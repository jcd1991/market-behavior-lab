"""Venue-aware market-microstructure contracts for research experiments.

This module is deliberately independent from Freqtrade.  Freqtrade OHLCV
remains the execution truth for candle backtests; this contract is for
optional one-minute trades and order-book data used to calibrate costs and to
run execution-sensitive simulations.  Missing fields fail closed instead of
being filled from another venue or from CoinGecko.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

SCHEMA_VERSION = "microstructure.v1"


def _timestamp(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_datetime(frame[name], utc=True, errors="coerce")
    raise ValueError(f"missing timestamp column; expected one of {names}")


def _number(frame: pd.DataFrame, *names: str, required: bool = True) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce")
    if required:
        raise ValueError(f"missing numeric column; expected one of {names}")
    return pd.Series(np.nan, index=frame.index, dtype=float)


def _canonical_pair(pair: str) -> str:
    value = str(pair or "").strip().upper()
    if "/" not in value:
        raise ValueError(f"invalid pair: {pair!r}")
    base, rest = value.split("/", 1)
    quote, separator, settlement = rest.partition(":")
    if separator:
        return f"{base}/{quote}:{settlement or quote}"
    return f"{base}/{quote}"


def normalize_minute_trades(
    frame: pd.DataFrame,
    *,
    venue: str,
    pair: str,
    source: str,
    market_type: str = "spot",
) -> pd.DataFrame:
    """Normalize exchange trades to the ``microstructure.v1`` trade schema."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["timestamp", "venue", "pair", "market_type", "price", "amount", "side", "notional", "source"])
    out = pd.DataFrame(
        {
            "timestamp": _timestamp(frame, "timestamp", "datetime", "date", "time"),
            "price": _number(frame, "price", "rate"),
            "amount": _number(frame, "amount", "quantity", "size", "volume"),
            "side": frame["side"].astype("string").str.lower() if "side" in frame else pd.Series(pd.NA, index=frame.index, dtype="string"),
        }
    )
    out["venue"] = str(venue).lower()
    out["pair"] = _canonical_pair(pair)
    out["market_type"] = str(market_type).lower()
    out["source"] = str(source)
    out["notional"] = out["price"].abs() * out["amount"].abs()
    out = out.dropna(subset=["timestamp", "price", "amount"])
    out = out[(out["price"] > 0) & (out["amount"] > 0)]
    return out[["timestamp", "venue", "pair", "market_type", "price", "amount", "side", "notional", "source"]].sort_values("timestamp").reset_index(drop=True)


def _levels(value: Any) -> list[list[float]]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, str):
        try:
            import json

            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    result: list[list[float]] = []
    for level in value or []:
        try:
            price, amount = float(level[0]), float(level[1])
        except (TypeError, ValueError, IndexError):
            continue
        if price > 0 and amount > 0:
            result.append([price, amount])
    return result


def normalize_orderbook_snapshots(
    frame: pd.DataFrame,
    *,
    venue: str,
    pair: str,
    source: str,
    market_type: str = "spot",
) -> pd.DataFrame:
    """Normalize L2 snapshots and retain enough depth for slippage replay.

    Input may provide ``bids``/``asks`` arrays or best bid/ask columns.  Array
    columns are kept as JSON-compatible lists so the output can be written to
    Parquet without losing depth information.
    """
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["timestamp", "venue", "pair", "market_type", "bids", "asks", "best_bid", "best_ask", "midpoint", "spread_bps", "source"])
    timestamps = _timestamp(frame, "timestamp", "datetime", "date", "time")
    rows: list[dict[str, Any]] = []
    for index, stamp in timestamps.items():
        if pd.isna(stamp):
            continue
        bids = _levels(frame.at[index, "bids"]) if "bids" in frame else []
        asks = _levels(frame.at[index, "asks"]) if "asks" in frame else []
        if not bids and "bid_price" in frame:
            bids = [[float(frame.at[index, "bid_price"]), float(frame.at[index, "bid_size"])]] if pd.notna(frame.at[index, "bid_price"]) and pd.notna(frame.at[index, "bid_size"]) else []
        if not asks and "ask_price" in frame:
            asks = [[float(frame.at[index, "ask_price"]), float(frame.at[index, "ask_size"])]] if pd.notna(frame.at[index, "ask_price"]) and pd.notna(frame.at[index, "ask_size"]) else []
        best_bid = bids[0][0] if bids else np.nan
        best_ask = asks[0][0] if asks else np.nan
        midpoint = (best_bid + best_ask) / 2.0 if best_bid and best_ask else np.nan
        spread_bps = (best_ask - best_bid) / midpoint * 10000.0 if midpoint and best_ask >= best_bid else np.nan
        rows.append({
            "timestamp": stamp, "venue": str(venue).lower(), "pair": _canonical_pair(pair),
            "market_type": str(market_type).lower(), "bids": bids, "asks": asks,
            "best_bid": best_bid, "best_ask": best_ask, "midpoint": midpoint,
            "spread_bps": spread_bps, "source": str(source),
        })
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def _walk(levels: Iterable[Iterable[float]], notional: float) -> tuple[float | None, float | None]:
    remaining = float(notional)
    filled = 0.0
    spent = 0.0
    for level in levels:
        try:
            price, amount = float(list(level)[0]), float(list(level)[1])
        except (TypeError, ValueError, IndexError):
            continue
        if price <= 0 or amount <= 0:
            continue
        value = min(remaining, price * amount)
        filled += value / price
        spent += value
        remaining -= value
        if remaining <= 1e-12:
            break
    if remaining > 1e-9 or filled <= 0:
        return None, None
    return spent / filled, filled


def depth_cost_bps(snapshot: dict[str, Any], *, side: str, notional: float) -> dict[str, float | None]:
    """Estimate spread and depth slippage for one aggressive execution."""
    bids = _levels(snapshot.get("bids"))
    asks = _levels(snapshot.get("asks"))
    if not bids or not asks or notional <= 0:
        return {"midpoint": None, "spread_bps": None, "slippage_bps": None, "filled": False}
    midpoint = (bids[0][0] + asks[0][0]) / 2.0
    levels = asks if side.lower() in {"buy", "long", "entry"} else bids
    vwap, filled = _walk(levels, notional)
    if vwap is None:
        return {"midpoint": midpoint, "spread_bps": (asks[0][0] - bids[0][0]) / midpoint * 10000.0, "slippage_bps": None, "filled": False}
    slippage = (vwap - midpoint) / midpoint * 10000.0 if side.lower() in {"buy", "long", "entry"} else (midpoint - vwap) / midpoint * 10000.0
    return {
        "midpoint": midpoint,
        "spread_bps": (asks[0][0] - bids[0][0]) / midpoint * 10000.0,
        "slippage_bps": max(0.0, float(slippage)),
        "filled": True,
        "filled_base": filled,
    }


def cost_curve(
    snapshots: pd.DataFrame,
    notionals: Iterable[float],
    *,
    side: str = "buy",
    costs: "VenueCostModel | None" = None,
    liquidity: str = "taker",
    tier: str | None = None,
) -> pd.DataFrame:
    """Return an observed spread/depth cost curve for each notional.

    The curve is descriptive: it shows what the supplied books could absorb
    at their timestamps. It does not backdate a current snapshot onto old
    Freqtrade trades.
    """
    rows: list[dict[str, Any]] = []
    for _, snapshot in snapshots.iterrows():
        payload = snapshot.to_dict()
        for notional in notionals:
            result = depth_cost_bps(payload, side=side, notional=float(notional))
            fee_bps = costs.fee_bps(liquidity=liquidity, tier=tier) if costs is not None else 0.0
            rows.append({
                "timestamp": snapshot.get("timestamp"),
                "venue": snapshot.get("venue"),
                "pair": snapshot.get("pair"),
                "side": side,
                "notional": float(notional),
                "fee_bps": fee_bps,
                "spread_bps": result.get("spread_bps"),
                "slippage_bps": result.get("slippage_bps"),
                "all_in_bps": None if result.get("slippage_bps") is None else fee_bps + float(result.get("slippage_bps") or 0.0) + float(costs.safety_bps if costs else 0.0),
                "filled": bool(result.get("filled")),
                "source": snapshot.get("source"),
            })
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class FeeTier:
    name: str
    maker_bps: float
    taker_bps: float
    minimum_30d_volume: float = 0.0


@dataclass(frozen=True)
class VenueCostModel:
    venue: str
    tiers: tuple[FeeTier, ...]
    default_tier: str
    safety_bps: float = 0.0

    def fee_bps(self, *, liquidity: str = "taker", tier: str | None = None) -> float:
        wanted = tier or self.default_tier
        selected = next((item for item in self.tiers if item.name == wanted), None)
        if selected is None:
            raise ValueError(f"unknown fee tier {wanted!r} for {self.venue}")
        return float(selected.maker_bps if liquidity.lower() == "maker" else selected.taker_bps)


def point_in_time_universe(
    candles: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    timestamp_col: str = "timestamp",
    effective_col: str = "effective_at",
    pair_col: str = "pair",
) -> pd.DataFrame:
    """Filter candles using membership known at each timestamp.

    Membership rows are effective from ``effective_at`` until the next row for
    that pair.  This prevents future listings or delistings from leaking into
    earlier rankings.  A missing membership table returns an empty frame to
    make an incomplete universe fail closed.
    """
    if candles is None or candles.empty or membership is None or membership.empty:
        return candles.iloc[0:0].copy() if candles is not None else pd.DataFrame()
    left = candles.copy()
    right = membership.copy()
    left[timestamp_col] = pd.to_datetime(left[timestamp_col], utc=True, errors="coerce")
    right[effective_col] = pd.to_datetime(right[effective_col], utc=True, errors="coerce")
    right[pair_col] = right[pair_col].map(_canonical_pair)
    right = right.dropna(subset=[effective_col]).sort_values([pair_col, effective_col])
    right["__next_effective"] = right.groupby(pair_col)[effective_col].shift(-1)
    left["__row"] = range(len(left))
    left[pair_col] = left[pair_col].map(_canonical_pair)
    joined = left.merge(right[[pair_col, effective_col, "__next_effective"]], on=pair_col, how="left")
    active = joined[timestamp_col].ge(joined[effective_col]) & (joined["__next_effective"].isna() | joined[timestamp_col].lt(joined["__next_effective"]))
    return joined.loc[active].sort_values("__row").drop(columns=["__row", effective_col, "__next_effective"]).reset_index(drop=True)
