"""Causal derivatives-conditioned momentum evaluator.

This lane is intentionally separate from a Freqtrade strategy.  It joins
same-venue candles with mark/index, funding, and open-interest observations
using their availability timestamps, then simulates next-bar entries with a
fixed holding period.  Missing or ambiguous derivative timestamps disable the
conditioning feature instead of silently filling it from another venue.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DerivativesMomentumPolicy:
    lookback: int = 48
    hold_bars: int = 12
    oi_window: int = 6
    min_momentum: float = 0.001
    min_oi_change: float = 0.0
    long_basis_max: float = 0.003
    short_basis_min: float = 0.003
    long_funding_max: float = 0.001
    short_funding_min: float = -0.001
    side: str = "both"
    max_positions: int = 2
    pair_weight: float = 0.50
    fee_bps_per_side: float = 4.0
    spread_bps_round_trip: float = 5.0
    slippage_bps_round_trip: float = 5.0

    @property
    def round_trip_cost(self) -> float:
        return (2.0 * self.fee_bps_per_side + self.spread_bps_round_trip + self.slippage_bps_round_trip) / 10000.0


def _utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def _read(path: Path, *, price_column: str = "close") -> pd.DataFrame:
    frame = pd.read_feather(path)
    if "date" not in frame or price_column not in frame:
        raise ValueError(f"{path} missing date/{price_column}")
    frame = frame.copy()
    frame["date"] = _utc(frame["date"])
    frame[price_column] = pd.to_numeric(frame[price_column], errors="coerce")
    return frame.dropna(subset=["date", price_column]).sort_values("date").drop_duplicates("date")


def _resample_ohlcv(frame: pd.DataFrame, rule: str = "5min") -> pd.DataFrame:
    work = frame.copy().set_index("date")
    aggregation = {
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }
    available = {column: method for column, method in aggregation.items() if column in work}
    out = work.resample(rule, label="left", closed="left").agg(available).dropna(subset=["close"]).reset_index()
    return out


def _available_source(frame: pd.DataFrame, value_columns: tuple[str, ...], *, required: bool) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["available_at", "value"])
    work = frame.copy()
    work["date"] = _utc(work["date"])
    stamp = "available_at" if "available_at" in work else "date"
    work["available_at"] = _utc(work[stamp])
    value = next((column for column in value_columns if column in work), None)
    if value is None:
        if required:
            raise ValueError(f"missing one of {value_columns}")
        return pd.DataFrame(columns=["available_at", "value"])
    work["value"] = pd.to_numeric(work[value], errors="coerce")
    return work[["available_at", "value"]].dropna().sort_values("available_at").drop_duplicates("available_at")


def prepare_features(
    candles: pd.DataFrame,
    *,
    mark: pd.DataFrame | None = None,
    index: pd.DataFrame | None = None,
    metrics: pd.DataFrame | None = None,
    funding: pd.DataFrame | None = None,
    rule: str = "5min",
) -> pd.DataFrame:
    """Build a causal 5-minute feature frame for one same-venue pair."""

    base = _resample_ohlcv(candles, rule=rule)
    base["momentum"] = base["close"].pct_change()
    base["momentum_n"] = base["close"].pct_change(48)

    def merge(name: str, source: pd.DataFrame | None, columns: tuple[str, ...], required: bool = False) -> None:
        values = _available_source(source, columns, required=required)
        if values.empty:
            base[name] = np.nan
            return
        left = base[["date"]].sort_values("date")
        right = values.rename(columns={"available_at": "date", "value": name})
        joined = pd.merge_asof(left, right, on="date", direction="backward")
        base[name] = pd.to_numeric(joined[name], errors="coerce").to_numpy()

    merge("mark_close", mark, ("mark_close", "mark_price", "close"))
    merge("index_close", index, ("index_close", "index_price", "close"))
    merge("open_interest", metrics, ("open_interest", "open_interest_amount", "oi"))
    merge("funding_rate", funding, ("funding_rate", "funding", "rate", "close"))
    base["basis"] = (base["mark_close"] - base["index_close"]) / base["index_close"].replace(0.0, np.nan)
    base["oi_change"] = base["open_interest"].pct_change()
    base["funding_rate"] = base["funding_rate"].ffill(limit=2)
    return base


def _drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    curve = pd.Series(values, dtype=float)
    return float(-(curve / curve.cummax() - 1.0).min() * 100.0)


def _simulate_pair(frame: pd.DataFrame, policy: DerivativesMomentumPolicy, *, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    work = frame.copy() if "basis" in frame.columns else _resample_ohlcv(frame, rule="5min")
    if start:
        work = work[work["date"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        work = work[work["date"] < pd.Timestamp(end, tz="UTC")]
    work = work.reset_index(drop=True)
    if len(work) <= max(policy.lookback, policy.hold_bars) + 2:
        return pd.DataFrame()
    momentum = work["close"].pct_change(policy.lookback)
    oi_change = work["open_interest"].pct_change(policy.oi_window)
    long_signal = (
        momentum.ge(policy.min_momentum)
        & oi_change.ge(policy.min_oi_change)
        & work["basis"].le(policy.long_basis_max)
        & work["funding_rate"].le(policy.long_funding_max)
    )
    short_signal = (
        momentum.le(-abs(policy.min_momentum))
        & oi_change.ge(policy.min_oi_change)
        & work["basis"].ge(policy.short_basis_min)
        & work["funding_rate"].ge(policy.short_funding_min)
    )
    if policy.side == "long":
        short_signal = short_signal & False
    elif policy.side == "short":
        long_signal = long_signal & False
    rows: list[dict[str, Any]] = []
    index = 0
    while index + policy.hold_bars < len(work) - 1:
        side = "long" if bool(long_signal.iloc[index]) else "short" if bool(short_signal.iloc[index]) else None
        if side is None:
            index += 1
            continue
        entry_index = index + 1
        exit_index = min(entry_index + policy.hold_bars, len(work) - 1)
        entry = float(work.iloc[entry_index]["open"] if "open" in work else work.iloc[entry_index]["close"])
        exit_price = float(work.iloc[exit_index]["close"])
        gross = exit_price / entry - 1.0 if side == "long" else entry / exit_price - 1.0
        rows.append({
            "pair": str(work.iloc[0].get("pair", "")), "side": side,
            "open_time": work.iloc[entry_index]["date"], "close_time": work.iloc[exit_index]["date"],
            "gross_ratio": gross, "profit_ratio": gross - policy.round_trip_cost,
            "momentum": float(momentum.iloc[index]), "oi_change": float(oi_change.iloc[index]),
            "basis": float(work.iloc[index]["basis"]), "funding_rate": float(work.iloc[index]["funding_rate"]),
        })
        index = exit_index
    return pd.DataFrame(rows)


def simulate(
    frames: dict[str, pd.DataFrame],
    policy: DerivativesMomentumPolicy = DerivativesMomentumPolicy(),
    *,
    start: str | None = None,
    end: str | None = None,
    starting_balance: float = 1000.0,
) -> dict[str, Any]:
    """Replay one shared wallet across same-venue derivative-conditioned trades."""

    trades = pd.concat(
        [_simulate_pair(frame, policy, start=start, end=end) for frame in frames.values()],
        ignore_index=True,
    ) if frames else pd.DataFrame()
    if trades.empty:
        return {"eligible": False, "reason": "no_signals", "policy": asdict(policy), "pairs": sorted(frames)}
    trades = trades.sort_values(["open_time", "close_time", "pair"]).reset_index(drop=True)
    balance = float(starting_balance)
    equity = [balance]
    active: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    rejected = 0
    for row in trades.to_dict("records"):
        still_open: list[dict[str, Any]] = []
        for position in active:
            if position["close_time"] <= row["open_time"]:
                balance += position["stake"] * float(position["profit_ratio"])
                equity.append(balance)
            else:
                still_open.append(position)
        active = still_open
        if len(active) >= policy.max_positions or any(position["pair"] == row["pair"] for position in active):
            rejected += 1
            continue
        stake = min(balance / max(1, policy.max_positions), balance * policy.pair_weight)
        if stake <= 0:
            rejected += 1
            continue
        position = {**row, "stake": stake}
        active.append(position)
        accepted.append(position)
    for position in sorted(active, key=lambda item: item["close_time"]):
        balance += position["stake"] * float(position["profit_ratio"])
        equity.append(balance)
    # Trade-level accounting is intentionally conservative and does not assume
    # the wallet can recycle unrealized PnL between overlapping positions.
    final_balance = balance
    accepted_returns = pd.Series([position["profit_ratio"] for position in accepted], dtype=float)
    return {
        "eligible": True, "policy": asdict(policy), "pairs": sorted(frames), "start": start, "end": end,
        "observations": int(sum(len(frame) for frame in frames.values())), "signals": int(len(trades)),
        "accepted": int(len(accepted)), "rejected": int(rejected),
        "final_balance": final_balance, "profit_abs": final_balance - starting_balance,
        "profit_pct": (final_balance / starting_balance - 1.0) * 100.0,
        "max_drawdown_pct": _drawdown(equity),
        "win_rate_pct": float((accepted_returns > 0).mean() * 100.0) if not accepted_returns.empty else 0.0,
        "long_trades": int((trades["side"] == "long").sum()), "short_trades": int((trades["side"] == "short").sum()),
        "cost_model": {"round_trip_bps": policy.round_trip_cost * 10000.0},
    }


def tune(
    frames: dict[str, pd.DataFrame],
    *,
    train_start: str,
    train_end: str,
    holdout_start: str,
    holdout_end: str | None = None,
) -> dict[str, Any]:
    grid = [
        DerivativesMomentumPolicy(lookback=lookback, hold_bars=hold, oi_window=oi_window, min_momentum=momentum, side=side)
        for lookback, hold, oi_window, momentum, side in itertools.product(
            (24, 48, 96), (6, 12, 24), (3, 6), (0.001, 0.002), ("long", "both")
        )
    ]
    candidates: list[dict[str, Any]] = []
    for policy in grid:
        result = simulate(frames, policy, start=train_start, end=train_end)
        score = (
            float(result.get("profit_pct", -1000.0))
            - 0.75 * float(result.get("max_drawdown_pct", 1000.0))
            if result.get("eligible") and result.get("accepted", 0) >= 5 else -100000.0
        )
        candidates.append({"policy": asdict(policy), "train": result, "score": score})
    selected = max(candidates, key=lambda row: row["score"])
    frozen = DerivativesMomentumPolicy(**selected["policy"])
    holdout = simulate(frames, frozen, start=holdout_start, end=holdout_end)
    return {
        "schema_version": "derivatives-momentum-tuning.v1", "train": {"start": train_start, "end": train_end},
        "holdout": {"start": holdout_start, "end": holdout_end}, "selected": selected["policy"],
        "selection_rule": "train profit minus 0.75x drawdown, minimum five accepted trades; frozen holdout",
        "tested": len(candidates), "top5": sorted(candidates, key=lambda row: row["score"], reverse=True)[:5],
        "holdout_result": holdout,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", action="append", required=True, help="pair=path to 1m/5m OHLCV")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frames = {}
    for value in args.candles:
        pair, raw_path = value.split("=", 1)
        frames[pair] = _resample_ohlcv(_read(Path(raw_path)), rule="5min")
    result = simulate(frames)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
