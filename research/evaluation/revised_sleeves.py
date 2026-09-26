"""Revised, data-gated research sleeves.

The functions in this module are intentionally offline and fail closed.  They
share one cost vocabulary and keep venue/source metadata in the result.  They
are not order routers and cannot turn incomplete historical data into an
execution-grade backtest.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExecutionCost:
    fee_bps_per_side: float = 10.0
    spread_bps_round_trip: float = 10.0
    slippage_bps_round_trip: float = 10.0
    safety_bps_round_trip: float = 5.0

    @property
    def round_trip_bps(self) -> float:
        return 2 * self.fee_bps_per_side + self.spread_bps_round_trip + self.slippage_bps_round_trip + self.safety_bps_round_trip


@dataclass(frozen=True)
class ResidualPolicy:
    window: int = 240
    entry_z: float = 1.8
    exit_z: float = 0.35
    min_corr: float = 0.75
    max_half_life: float = 120.0
    leg_round_trip_cost_bps: float = 30.0


def _utc(frame: pd.DataFrame, column: str = "date") -> pd.DataFrame:
    work = frame.copy()
    if column not in work.columns:
        raise ValueError(f"missing {column} column")
    work[column] = pd.to_datetime(work[column], utc=True, errors="coerce").astype("datetime64[ns, UTC]")
    return work.dropna(subset=[column]).sort_values(column).drop_duplicates(column).reset_index(drop=True)


def _price(frame: pd.DataFrame, name: str = "close") -> pd.Series:
    if name not in frame.columns:
        raise ValueError(f"missing {name} column")
    return pd.to_numeric(frame[name], errors="coerce")


def evaluate_carry_contract(
    spot: pd.DataFrame | None,
    perp: pd.DataFrame | None,
    funding: pd.DataFrame | None,
    index: pd.DataFrame | None,
    *,
    venue: str,
    costs: ExecutionCost = ExecutionCost(),
    min_basis: float = 0.005,
    exit_basis: float = 0.001,
    min_funding: float = 0.0001,
    min_margin_buffer: float = 0.20,
) -> dict[str, Any]:
    """Validate exact-venue cash-and-carry inputs and estimate a simple path.

    Funding is counted only at funding observation timestamps, avoiding the
    common error of adding the last observed funding rate to every candle.
    Spot and perp prices are modeled as two legs; no CoinGecko or other-venue
    substitute is accepted.
    """
    frames = {"spot": spot, "perp": perp, "funding": funding, "index": index}
    missing = [name for name, frame in frames.items() if frame is None or frame.empty]
    if missing:
        return {"eligible": False, "reason": "missing_input", "missing": missing, "venue": venue}
    prepared = {name: _utc(frame) for name, frame in frames.items() if frame is not None}
    for name, frame in prepared.items():
        if "close" not in frame.columns and name == "index" and "index_close" in frame.columns:
            frame["close"] = frame["index_close"]
        if "close" not in frame.columns and name == "funding" and "funding_rate" in frame.columns:
            frame["close"] = frame["funding_rate"]
    if "close" not in prepared["spot"].columns or "close" not in prepared["perp"].columns or "close" not in prepared["index"].columns:
        return {"eligible": False, "reason": "price_column_missing", "venue": venue}
    funding_col = next((column for column in ("funding_rate", "funding", "rate", "close") if column in prepared["funding"].columns), None)
    if funding_col is None:
        return {"eligible": False, "reason": "funding_column_missing", "venue": venue}
    left = prepared["spot"][["date", "close"]].rename(columns={"close": "spot_close"})
    right = prepared["perp"][["date", "close"]].rename(columns={"close": "perp_close"})
    idx = prepared["index"][["date", "close"]].rename(columns={"close": "index_close"})
    merged = pd.merge_asof(left, right, on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    merged = pd.merge_asof(merged, idx, on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    rates = prepared["funding"][["date", funding_col]].rename(columns={funding_col: "funding_rate"})
    rates["funding_rate"] = pd.to_numeric(rates["funding_rate"], errors="coerce")
    rates = rates.dropna(subset=["funding_rate"]).sort_values("date").reset_index(drop=True)
    # Use the latest observed rate only for the entry/exit signal.  Carry
    # income is summed from actual funding timestamps below, so a sparse file
    # cannot be mistaken for a continuously paid rate.
    merged = pd.merge_asof(merged, rates, on="date", direction="backward", tolerance=pd.Timedelta("8h"))
    margin_col = next((column for column in ("margin_buffer", "liquidation_distance", "liquidation_buffer") if column in prepared["perp"].columns), None)
    if margin_col:
        margin = prepared["perp"][["date", margin_col]].rename(columns={margin_col: "margin_buffer"})
        merged = pd.merge_asof(merged, margin, on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    else:
        merged["margin_buffer"] = np.nan
    merged["basis"] = merged["perp_close"] / merged["index_close"] - 1.0
    merged = merged.dropna(subset=["spot_close", "perp_close", "index_close"]).reset_index(drop=True)
    if merged.empty:
        return {"eligible": False, "reason": "no_exact_overlap", "venue": venue}
    held = False
    entry_basis = 0.0
    entry_time: pd.Timestamp | None = None
    entries = 0
    exits = 0
    carry_returns: list[float] = []
    funding_observations_used = 0

    def funding_between(start: pd.Timestamp, end: pd.Timestamp) -> float:
        nonlocal funding_observations_used
        observed = rates[rates["date"].gt(start) & rates["date"].le(end)]
        funding_observations_used += len(observed)
        return float(observed["funding_rate"].sum())

    for row in merged.itertuples():
        margin_ok = pd.isna(row.margin_buffer) or float(row.margin_buffer) >= min_margin_buffer
        signal = pd.notna(row.funding_rate) and float(row.basis) >= min_basis and float(row.funding_rate) >= min_funding
        exit_signal = float(row.basis) <= exit_basis or (pd.notna(row.funding_rate) and float(row.funding_rate) < 0.0)
        if not held and signal and margin_ok:
            held = True
            entry_basis = float(row.basis)
            entry_time = row.date
            entries += 1
        elif held and exit_signal:
            funding_income = funding_between(entry_time, row.date) if entry_time is not None else 0.0
            carry_returns.append(entry_basis - float(row.basis) + funding_income - costs.round_trip_bps / 10000.0)
            held = False
            entry_time = None
            exits += 1
    if held:
        last = merged.iloc[-1]
        funding_income = funding_between(entry_time, last["date"]) if entry_time is not None else 0.0
        carry_returns.append(entry_basis - float(last["basis"]) + funding_income - costs.round_trip_bps / 10000.0)
        exits += 1
    return {
        "eligible": True,
        "venue": venue,
        "observations": int(len(merged)),
        "entries": entries,
        "closed_or_force_closed": exits,
        "funding_observations_used": funding_observations_used,
        "basis_mean": float(merged["basis"].mean()),
        "funding_mean": float(merged["funding_rate"].mean()),
        "profit_ratio": float(np.sum(carry_returns)),
        "profit_pct": float(np.sum(carry_returns) * 100.0),
        "margin_buffer_available": bool(merged["margin_buffer"].notna().any()),
        "costs": asdict(costs),
        "venue_provenance": "same-venue inputs required",
    }


def _residual_features(asset: pd.Series, reference: pd.Series, window: int) -> pd.DataFrame:
    y = np.log(asset.replace(0, np.nan))
    x = np.log(reference.replace(0, np.nan))
    beta = (y.rolling(window).cov(x) / x.rolling(window).var().replace(0, np.nan)).clip(0.05, 5.0)
    residual = y - beta * x
    mean = residual.rolling(window).mean()
    std = residual.rolling(window).std().replace(0, np.nan)
    lag = residual.shift(1)
    slope = residual.diff().rolling(window).cov(lag) / lag.rolling(window).var().replace(0, np.nan)
    half_life = (-np.log(2.0) / slope).where(slope < 0)
    return pd.DataFrame({"beta": beta, "z": (residual - mean) / std, "corr": y.rolling(window).corr(x), "half_life": half_life})


def simulate_two_leg_residual(asset: pd.DataFrame, reference: pd.DataFrame, *, venue: str, policy: ResidualPolicy = ResidualPolicy()) -> dict[str, Any]:
    """Replay a synchronized long/short pair with explicit two-leg costs."""
    left = _utc(asset)[["date", "close"]].rename(columns={"close": "asset_close"})
    right = _utc(reference)[["date", "close"]].rename(columns={"close": "reference_close"})
    joined = left.merge(right, on="date", how="inner").dropna()
    if len(joined) < policy.window + 2:
        return {"eligible": False, "reason": "insufficient_overlap", "observations": int(len(joined)), "venue": venue}
    features = _residual_features(joined["asset_close"], joined["reference_close"], policy.window)
    asset_ret = joined["asset_close"].pct_change().fillna(0.0)
    ref_ret = joined["reference_close"].pct_change().fillna(0.0)
    leg_cost = policy.leg_round_trip_cost_bps / 10000.0
    equity = 1.0
    state = 0
    beta_weight = 0.0
    entries = 0
    exits = 0
    curve = [equity]
    both_leg_pnl = {"asset_leg": 0.0, "reference_leg": 0.0}
    for index in range(1, len(joined)):
        if state:
            asset_leg = state * (1.0 - beta_weight) * float(asset_ret.iloc[index])
            reference_leg = -state * beta_weight * float(ref_ret.iloc[index])
            equity *= max(0.0, 1.0 + asset_leg + reference_leg)
            both_leg_pnl["asset_leg"] += asset_leg
            both_leg_pnl["reference_leg"] += reference_leg
        row = features.iloc[index]
        valid = pd.notna(row["z"]) and pd.notna(row["corr"]) and pd.notna(row["half_life"]) and float(row["corr"]) >= policy.min_corr and 0.0 < float(row["half_life"]) <= policy.max_half_life
        z = float(row["z"]) if pd.notna(row["z"]) else np.nan
        if state and (abs(z) <= policy.exit_z or not valid):
            equity *= max(0.0, 1.0 - leg_cost)
            state = 0
            beta_weight = 0.0
            exits += 1
        elif not state and valid and abs(z) >= policy.entry_z:
            state = 1 if z < 0 else -1
            beta = min(5.0, max(0.05, abs(float(row["beta"]))))
            beta_weight = beta / (1.0 + beta)
            equity *= max(0.0, 1.0 - leg_cost)
            entries += 1
        curve.append(equity)
    if state:
        equity *= max(0.0, 1.0 - leg_cost)
        exits += 1
        curve[-1] = equity
    series = pd.Series(curve, index=joined["date"])
    return {
        "eligible": True,
        "venue": venue,
        "observations": int(len(joined)),
        "entries": entries,
        "closed_or_force_closed": exits,
        "profit_pct": float((equity - 1.0) * 100.0),
        "max_drawdown_pct": float((series / series.cummax() - 1.0).min() * -100.0),
        "leg_pnl_proxy": both_leg_pnl,
        "policy": asdict(policy),
        "execution": "synchronized two-leg close-price screen; not a broker fill simulation",
    }


def apply_execution_gate(trades: pd.DataFrame, *, costs: ExecutionCost = ExecutionCost(), minimum_volume_ratio: float = 0.75, expected_move_column: str = "expected_move_bps") -> dict[str, Any]:
    """Reject signals whose forecast move does not cover all-in execution cost."""
    required = {expected_move_column, "volume_ratio"}
    if not required.issubset(trades.columns):
        return {"eligible": False, "reason": "missing_columns", "missing": sorted(required - set(trades.columns))}
    frame = trades.copy()
    frame["expected_move_bps"] = pd.to_numeric(frame[expected_move_column], errors="coerce")
    frame["volume_ratio"] = pd.to_numeric(frame["volume_ratio"], errors="coerce")
    frame["all_in_cost_bps"] = costs.round_trip_bps
    accepted = frame[frame["expected_move_bps"].ge(frame["all_in_cost_bps"]) & frame["volume_ratio"].ge(minimum_volume_ratio)].copy()
    return {
        "eligible": True,
        "input": int(len(frame)),
        "accepted": int(len(accepted)),
        "rejected": int(len(frame) - len(accepted)),
        "acceptance_rate": float(len(accepted) / len(frame)) if len(frame) else 0.0,
        "all_in_cost_bps": costs.round_trip_bps,
        "minimum_volume_ratio": minimum_volume_ratio,
        "accepted_trades": accepted.to_dict(orient="records"),
    }


def lead_lag_screen(leader: pd.DataFrame, follower: pd.DataFrame, *, leader_name: str, follower_name: str, interval: str = "1min", max_lag_steps: int = 5, costs: ExecutionCost = ExecutionCost()) -> dict[str, Any]:
    """Screen a causal lead-lag signal from synchronized event prices."""
    required = {"timestamp", "price"}
    if not required.issubset(leader.columns) or not required.issubset(follower.columns):
        return {"eligible": False, "reason": "missing_event_columns", "required": sorted(required)}
    a = _utc(leader, "timestamp").set_index("timestamp")["price"].astype(float).resample(interval).last().dropna()
    b = _utc(follower, "timestamp").set_index("timestamp")["price"].astype(float).resample(interval).last().dropna()
    joined = pd.concat([a.rename("leader"), b.rename("follower")], axis=1).dropna()
    if len(joined) < max(20, max_lag_steps + 5):
        return {"eligible": False, "reason": "insufficient_overlap", "observations": int(len(joined)), "leader": leader_name, "follower": follower_name}
    leader_returns = joined["leader"].pct_change()
    follower_returns = joined["follower"].pct_change()
    rows = []
    for lag in range(1, max_lag_steps + 1):
        signal = leader_returns.shift(lag)
        pair = pd.concat([signal.rename("signal"), follower_returns.rename("return")], axis=1).dropna()
        pnl = np.sign(pair["signal"]) * pair["return"] - costs.round_trip_bps / 10000.0
        rows.append({"lag_steps": lag, "correlation": float(pair["signal"].corr(pair["return"])), "observations": int(len(pair)), "screen_profit_pct": float(pnl.sum() * 100.0), "positive_fraction": float((pnl > 0).mean())})
    best = max(rows, key=lambda row: row["screen_profit_pct"])
    return {"eligible": True, "leader": leader_name, "follower": follower_name, "interval": interval, "observations": int(len(joined)), "lags": rows, "best_lag": best, "warning": "diagnostic event screen only; current captures are not historical execution data"}


def validate_option_history(frame: pd.DataFrame | None) -> dict[str, Any]:
    required = {"timestamp", "instrument", "option_type", "strike", "expiry", "bid", "ask", "mark_iv", "delta", "underlying_price"}
    if frame is None or frame.empty:
        return {"eligible": False, "reason": "missing_option_history", "missing": sorted(required)}
    missing = sorted(required - set(frame.columns))
    return {"eligible": not missing, "reason": "missing_columns" if missing else "ok", "missing": missing, "rows": int(len(frame)), "source": "option-chain-history-required"}


def evaluate_delta_hedged_straddle(frame: pd.DataFrame | None, *, entry_iv: float = 0.70, holding_periods: int = 6, costs: ExecutionCost = ExecutionCost()) -> dict[str, Any]:
    """Evaluate a minimal short ATM straddle only when option history exists."""
    validation = validate_option_history(frame)
    if not validation["eligible"]:
        return {**validation, "strategy": "delta_hedged_short_straddle"}
    work = _utc(frame, "timestamp").copy()
    work["mid"] = (pd.to_numeric(work["bid"], errors="coerce") + pd.to_numeric(work["ask"], errors="coerce")) / 2.0
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    candidates = work[pd.to_numeric(work["mark_iv"], errors="coerce").ge(entry_iv)].sort_values("timestamp")
    if candidates.empty:
        return {**validation, "strategy": "delta_hedged_short_straddle", "eligible": False, "reason": "no_iv_signal"}
    returns: list[float] = []
    for instrument, group in candidates.groupby("instrument"):
        group = group.sort_values("timestamp").reset_index(drop=True)
        for index in range(len(group) - holding_periods):
            start = group.iloc[index]
            end = group.iloc[index + holding_periods]
            option_change = float(end["mid"] - start["mid"])
            delta_hedge = -float(start["delta"])
            underlying_change = float(end["underlying_price"] - start["underlying_price"])
            returns.append(-option_change + delta_hedge * underlying_change - costs.round_trip_bps / 10000.0 * float(start["mid"]))
    return {"eligible": bool(returns), "strategy": "delta_hedged_short_straddle", "observations": int(len(work)), "simulated_trades": len(returns), "profit_abs_proxy": float(np.sum(returns)), "warning": "single-option path approximation; requires paired call/put and hedge fills for promotion"}
