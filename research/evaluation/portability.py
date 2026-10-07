"""Frozen portability evaluators for a native OKX spot candle panel.

This module deliberately treats portability as a data and execution gate.  It
does not tune on OKX, merge venues, or treat the short OKX websocket capture as
historical fill evidence.  The cross-sectional policy was selected before this
run from the prior Binance.US screen; the breakout and volatility parameters
are the saved slow research candidates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from research.evaluation.cross_sectional_portfolio import (
    PortfolioPolicy,
    build_features,
    simulate_portfolio,
)
from research.evaluation.recommended_lanes import (
    BreakoutPolicy,
    CostModel,
    _trade_frame,
)
from research.evaluation.volatility_ensemble import SleeveSpec, evaluate_frozen_sleeves


OKX_PAIRS: tuple[str, ...] = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "DOGE/USDT",
)


@dataclass(frozen=True)
class VmtPolicy:
    """Frozen values from VolatilityManagedTrendCashSpot.json."""

    fast: int = 72
    slow: int = 281
    min_score: float = 0.92
    max_vol: float = 2.33
    target_vol: float = 0.14
    min_edge: float = 0.001
    min_liq_ratio: float = 1.95
    min_quote_volume: float = 100_000.0
    cost_floor: float = 0.005


def _read_candle(path: Path, pair: str) -> pd.DataFrame:
    frame = pd.read_feather(path).copy()
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "open", "high", "low", "close"])
    frame = frame.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    frame["pair"] = pair
    return frame


def load_okx_spot(data_dir: Path, pairs: Iterable[str] = OKX_PAIRS) -> dict[str, pd.DataFrame]:
    """Load the native OKX spot files without filling missing candles."""

    output: dict[str, pd.DataFrame] = {}
    for pair in pairs:
        path = data_dir / f"{pair.replace('/', '_')}-15m.feather"
        if path.is_file():
            output[pair] = _read_candle(path, pair)
    return output


def resample_ohlcv(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample complete native candles using left-labelled UTC bars.

    A partial final bar is discarded. This matters when a native download ends
    between higher-timeframe boundaries: using that bar would make the last
    signal/fill incomparable with a normal completed candle.
    """

    if frame.empty:
        return frame.copy()
    work = frame.copy().set_index("date").sort_index()
    bucket = work.resample(rule, label="left", closed="left")
    result = bucket.agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    expected = int(pd.Timedelta(rule).total_seconds() // pd.Timedelta("15min").total_seconds())
    result["_bar_count"] = bucket["close"].count()
    result = result[result["_bar_count"].eq(expected)]
    result = result.dropna(subset=["open", "high", "low", "close"]).drop(columns=["_bar_count"]).reset_index()
    result["pair"] = str(frame["pair"].iloc[0])
    return result[["date", "open", "high", "low", "close", "volume", "pair"]]


def build_static_membership(pairs: Iterable[str], effective_at: str = "2024-06-01T00:00:00Z") -> pd.DataFrame:
    """Build an explicit static screen universe; this is not PIT membership."""

    return pd.DataFrame(
        [{"pair": pair, "effective_at": effective_at} for pair in pairs],
        columns=["pair", "effective_at"],
    )


def synchronized_panel(candles: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Audit whether the native pair files share one timestamp grid."""

    grids = {pair: pd.DatetimeIndex(frame["date"]) for pair, frame in candles.items()}
    if not grids:
        return {"synchronized": False, "pairs": [], "reason": "no_candles"}
    reference = next(iter(grids.values()))
    mismatches = {
        pair: {"rows": len(index), "missing_from_reference": int(len(reference.difference(index)))}
        for pair, index in grids.items()
        if not index.equals(reference)
    }
    return {
        "synchronized": not mismatches,
        "pairs": sorted(grids),
        "rows_per_pair": {pair: len(index) for pair, index in grids.items()},
        "start": reference.min().isoformat(),
        "end": reference.max().isoformat(),
        "mismatches": mismatches,
    }


def equal_weight_buy_hold(candles: dict[str, pd.DataFrame], *, starting_balance: float = 1000.0) -> dict[str, Any]:
    """No-trading-cost equal-weight buy-and-hold reference."""

    if not candles:
        return {"eligible": False, "reason": "no_candles"}
    series = []
    for pair, frame in candles.items():
        close = frame.set_index("date")["close"].astype(float).rename(pair)
        series.append(close)
    panel = pd.concat(series, axis=1).dropna()
    if panel.empty:
        return {"eligible": False, "reason": "no_common_timestamps"}
    returns = panel.iloc[-1] / panel.iloc[0] - 1.0
    final = starting_balance * float((1.0 + returns).mean())
    return {
        "eligible": True,
        "starting_balance": starting_balance,
        "final_balance": final,
        "profit_pct": (final / starting_balance - 1.0) * 100.0,
        "pairs": sorted(panel.columns),
        "start": panel.index[0].isoformat(),
        "end": panel.index[-1].isoformat(),
        "costs": "none; reference only",
    }


def _window(frame: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    work = frame
    if start:
        work = work[work["timestamp"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        work = work[work["timestamp"] < pd.Timestamp(end, tz="UTC")]
    return work.copy()


def evaluate_cross_sectional(
    candles_1h: dict[str, pd.DataFrame],
    *,
    policy: PortfolioPolicy,
    costs: dict[str, float] | None = None,
    starting_balance: float = 1000.0,
) -> dict[str, Any]:
    """Evaluate the frozen slower cross-sectional policy on OKX."""

    rows = []
    for pair, frame in candles_1h.items():
        rows.append(frame[["date", "pair", "close", "volume"]].rename(columns={"date": "timestamp"}))
    candles = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    membership = build_static_membership(candles_1h)
    features = build_features(candles, membership, policy=policy)
    result = simulate_portfolio(features, policy=policy, spot_only=True, starting_balance=starting_balance)
    windows = {
        "early": ("2024-06-01", "2025-12-01"),
        "forward": ("2025-12-01", None),
    }
    result["windows"] = {
        name: simulate_portfolio(
            _window(features, start, end), policy=policy, spot_only=True, starting_balance=starting_balance
        )
        for name, (start, end) in windows.items()
    }
    result["policy"] = asdict(policy)
    result["costs"] = costs or {
        "fee_bps_per_side": policy.fee_bps,
        "spread_bps_round_trip": policy.spread_bps,
        "slippage_bps_round_trip": policy.slippage_bps,
        "cost_note": "modeled; no historical OKX fill curve was available",
    }
    result["universe_method"] = "static five-pair screen; point-in-time listings and liquidity membership unavailable"
    return result


def _breakout_trades(candles_4h: dict[str, pd.DataFrame], policy: BreakoutPolicy) -> pd.DataFrame:
    zero_cost = CostModel(fee_bps_per_side=0.0, spread_bps_round_trip=0.0, slippage_bps_round_trip=0.0)
    rows = []
    for pair, frame in candles_4h.items():
        work = frame.copy()
        trades = _trade_frame(work, policy, zero_cost, side="long")
        if not trades.empty:
            trades["sleeve"] = "slow_breakout"
            trades["profit_ratio"] = trades["gross_ratio"]
            rows.append(trades[["sleeve", "pair", "open_time", "close_time", "profit_ratio"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["sleeve", "pair", "open_time", "close_time", "profit_ratio"])


def _vmt_trades(frame: pd.DataFrame, policy: VmtPolicy) -> pd.DataFrame:
    """Reconstruct the long-only VMT signal rules causally from OHLCV."""

    work = frame.copy().sort_values("date").reset_index(drop=True)
    close = work["close"].astype(float)
    returns = close.pct_change()
    vol = returns.rolling(48, min_periods=24).std() * np.sqrt(24 * 365)
    fast_ema = close.ewm(span=policy.fast, adjust=False, min_periods=policy.fast).mean()
    slow_ema = close.ewm(span=policy.slow, adjust=False, min_periods=policy.slow).mean()
    normalized_slope = (fast_ema / slow_ema - 1.0) / vol.replace(0.0, np.nan)
    momentum = close.pct_change(policy.fast) / vol.replace(0.0, np.nan)
    score = (np.sign(normalized_slope) + np.sign(momentum)) * 0.5
    scale = (policy.target_vol / vol.replace(0.0, np.nan)).clip(0.20, 1.25).fillna(0.20)
    risk_on = vol.le(policy.max_vol)
    expected_move = close.pct_change(policy.fast).abs()
    quote = close.abs() * work["volume"].clip(lower=0.0)
    median_quote = quote.rolling(48, min_periods=24).median().replace(0.0, np.nan)
    volume_ratio = quote / median_quote
    liquid = quote.ge(policy.min_quote_volume) & volume_ratio.ge(policy.min_liq_ratio)
    active = risk_on & liquid & expected_move.ge(policy.cost_floor + policy.min_edge)
    entry_signal = active & score.ge(policy.min_score)
    exit_signal = (~risk_on) | score.lt(0.0)
    rows: list[dict[str, Any]] = []
    open_index: int | None = None
    for index in range(len(work) - 1):
        if open_index is None and bool(entry_signal.iloc[index]):
            open_index = index + 1
            continue
        if open_index is None or index <= open_index:
            continue
        if bool(exit_signal.iloc[index]) or index == len(work) - 2:
            close_index = min(index + 1, len(work) - 1)
            entry = float(work.iloc[open_index]["open"])
            exit_price = float(work.iloc[close_index]["open"])
            gross = exit_price / entry - 1.0
            rows.append(
                {
                    "sleeve": "volatility_trend_cash",
                    "pair": str(work.iloc[0]["pair"]),
                    "open_time": work.iloc[open_index]["date"],
                    "close_time": work.iloc[close_index]["date"],
                    "profit_ratio": float(gross * float(scale.iloc[open_index])),
                    "size_scale": float(scale.iloc[open_index]),
                }
            )
            open_index = None
    return pd.DataFrame(rows, columns=["sleeve", "pair", "open_time", "close_time", "profit_ratio", "size_scale"])


def evaluate_breakout_volatility(
    candles_1h: dict[str, pd.DataFrame],
    candles_4h: dict[str, pd.DataFrame],
    *,
    fee_bps: float = 10.0,
    spread_bps: float = 5.0,
    slippage_bps: float = 5.0,
    starting_balance: float = 1000.0,
) -> dict[str, Any]:
    """Evaluate frozen slow breakout and VMT sleeves plus their shared wallet."""

    breakout_policy = BreakoutPolicy(
        horizons=(18, 36, 72, 144),
        votes=2,
        atr_max=0.20,
        breakout_buffer=0.002,
        exit_ema=24,
    )
    vmt_policy = VmtPolicy()
    breakout = _breakout_trades(candles_4h, breakout_policy)
    vmt_rows = [_vmt_trades(frame, vmt_policy) for frame in candles_1h.values()]
    vmt = pd.concat([row for row in vmt_rows if not row.empty], ignore_index=True) if any(not row.empty for row in vmt_rows) else pd.DataFrame(columns=["sleeve", "pair", "open_time", "close_time", "profit_ratio", "size_scale"])
    all_trades = pd.concat([breakout, vmt[["sleeve", "pair", "open_time", "close_time", "profit_ratio"]]], ignore_index=True)
    cost_args = {"starting_balance": starting_balance, "max_open_positions": 3, "fee_bps": fee_bps, "spread_bps": spread_bps, "slippage_bps": slippage_bps}
    specs = (SleeveSpec("slow_breakout", 0.50, 0.25), SleeveSpec("volatility_trend_cash", 0.50, 0.25))
    combined = evaluate_frozen_sleeves(all_trades, specs, **cost_args)
    singles = {
        name: evaluate_frozen_sleeves(
            all_trades[all_trades["sleeve"] == name], (SleeveSpec(name, 1.0, 0.25),), **cost_args
        )
        for name in ("slow_breakout", "volatility_trend_cash")
    }
    train_end = pd.Timestamp("2025-12-01", tz="UTC")
    forward_trades = all_trades[pd.to_datetime(all_trades["close_time"], utc=True) >= train_end]
    forward = evaluate_frozen_sleeves(forward_trades, specs, **cost_args)
    return {
        "breakout_policy": asdict(breakout_policy),
        "vmt_policy": asdict(vmt_policy),
        "costs": {"fee_bps_per_side": fee_bps, "spread_bps_round_trip": spread_bps, "slippage_bps_round_trip": slippage_bps, "note": "modeled; no full-period OKX fill curve"},
        "trade_counts": {"slow_breakout": int(len(breakout)), "volatility_trend_cash": int(len(vmt)), "combined": int(len(all_trades))},
        "singles": singles,
        "shared_wallet_full": combined,
        "shared_wallet_forward": forward,
        "decision": "research_only_until_trade_level_OKX_data_and_more_unseen_venue_windows",
    }


def load_capture_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"available": False, "path": str(path)}
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "available": True,
        "path": str(path),
        "venue": payload.get("venue"),
        "market_type": payload.get("market_type"),
        "pairs": payload.get("pairs", []),
        "message_count": payload.get("message_count", 0),
        "requested_seconds": payload.get("requested_seconds"),
        "started_at": payload.get("started_at"),
        "ended_at": payload.get("ended_at"),
        "execution_truth": payload.get("execution_truth", False),
        "status": payload.get("status"),
        "source": payload.get("source"),
    }


def build_data_quality_report(data_dir: Path, *, capture_manifest: Path | None = None) -> dict[str, Any]:
    candles = load_okx_spot(data_dir)
    quality = synchronized_panel(candles)
    quality.update(
        {
            "venue": "okx",
            "market_type": "spot",
            "native_timeframe": "15m",
            "source": "local Freqtrade-style OKX candle files",
            "execution_truth": False,
            "unseen_for_frozen_policies": True,
            "unseen_venue_globally": False,
            "minute_trade_history_available": False,
            "full_period_l2_history_available": False,
            "pit_universe_available": False,
        }
    )
    if capture_manifest:
        quality["microstructure_capture"] = load_capture_manifest(capture_manifest)
    return quality
