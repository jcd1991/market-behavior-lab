"""Point-in-time, cost-aware cross-sectional portfolio research lane.

This is an offline portfolio evaluator, not a Freqtrade strategy.  It exists
because a per-pair strategy cannot express a genuine shared-wallet ranking,
beta budget, or concentration cap without an allocator above the strategy
interface.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from .microstructure import point_in_time_universe
except ImportError:  # Script execution from research/evaluation.
    from microstructure import point_in_time_universe


@dataclass(frozen=True)
class PortfolioPolicy:
    lookback: int = 72
    reversal_window: int = 12
    volatility_window: int = 48
    rebalance_every: int = 6
    longs: int = 3
    shorts: int = 0
    target_vol: float = 0.30
    max_pair_weight: float = 0.25
    max_abs_beta: float = 0.35
    fee_bps: float = 10.0
    spread_bps: float = 5.0
    slippage_bps: float = 5.0


def build_features(candles: pd.DataFrame, membership: pd.DataFrame, *, policy: PortfolioPolicy = PortfolioPolicy()) -> pd.DataFrame:
    required = {"pair", "close", "volume"}
    if not required.issubset(candles.columns):
        raise ValueError(f"candles missing columns: {sorted(required - set(candles.columns))}")
    frame = candles.copy()
    frame["timestamp"] = pd.to_datetime(frame.get("timestamp", frame.get("date")), utc=True, errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    frame = point_in_time_universe(frame.dropna(subset=["timestamp", "close"]), membership)
    if frame.empty:
        return frame.assign(momentum=[], reversal=[], volatility=[], liquidity=[], beta=[], score=[])
    frame = frame.sort_values(["pair", "timestamp"]).reset_index(drop=True)
    grouped = frame.groupby("pair", group_keys=False)
    returns = grouped["close"].pct_change()
    frame["momentum"] = grouped["close"].pct_change(policy.lookback)
    frame["reversal"] = -grouped["close"].pct_change(policy.reversal_window)
    frame["volatility"] = returns.groupby(frame["pair"]).transform(lambda s: s.rolling(policy.volatility_window, min_periods=max(8, policy.volatility_window // 2)).std() * np.sqrt(24 * 365))
    frame["liquidity"] = (frame["close"].abs() * frame["volume"].clip(lower=0)).groupby(frame["pair"]).transform(lambda s: s.rolling(policy.volatility_window, min_periods=max(8, policy.volatility_window // 2)).median())
    btc = frame[frame["pair"].str.startswith("BTC/")][["timestamp", "close"]].drop_duplicates("timestamp").set_index("timestamp")["close"].pct_change()
    frame["beta"] = np.nan
    for pair, indices in frame.groupby("pair").groups.items():
        local = frame.loc[indices].set_index("timestamp")["close"].pct_change()
        joined = pd.concat([local.rename("asset"), btc.rename("btc")], axis=1)
        beta = joined["asset"].rolling(policy.volatility_window, min_periods=max(8, policy.volatility_window // 2)).cov(joined["btc"]) / joined["btc"].rolling(policy.volatility_window, min_periods=max(8, policy.volatility_window // 2)).var()
        frame.loc[indices, "beta"] = beta.reindex(frame.loc[indices, "timestamp"]).to_numpy()
    for column in ("momentum", "reversal", "liquidity"):
        frame[f"{column}_rank"] = frame.groupby("timestamp")[column].rank(pct=True)
    frame["vol_rank"] = frame.groupby("timestamp")["volatility"].rank(pct=True, ascending=False)
    frame["score"] = (0.45 * frame["momentum_rank"] + 0.20 * frame["liquidity_rank"] + 0.15 * frame["reversal_rank"] + 0.20 * (1.0 - frame["vol_rank"]))
    return frame


def _weights(rows: pd.DataFrame, *, direction: int, policy: PortfolioPolicy) -> dict[str, float]:
    if rows.empty:
        return {}
    ordered = rows.sort_values("score", ascending=direction < 0)
    count = policy.longs if direction > 0 else policy.shorts
    selected = ordered.head(max(0, count)).dropna(subset=["volatility"])
    if selected.empty:
        return {}
    raw = 1.0 / selected["volatility"].clip(lower=0.05)
    raw = raw / raw.sum()
    weights = {str(pair): float(min(policy.max_pair_weight, value)) * direction for pair, value in zip(selected["pair"], raw)}
    total = sum(abs(value) for value in weights.values())
    if total > 1.0:
        weights = {pair: value / total for pair, value in weights.items()}
    vol_by_pair = {str(pair): float(vol) for pair, vol in zip(selected["pair"], selected["volatility"])}
    estimated_portfolio_vol = sum(abs(value) * vol_by_pair.get(pair, 0.0) for pair, value in weights.items())
    if estimated_portfolio_vol > 0 and policy.target_vol > 0:
        target_scale = min(1.0, policy.target_vol / estimated_portfolio_vol)
        weights = {pair: value * target_scale for pair, value in weights.items()}
    beta = sum(float(selected.loc[selected["pair"] == pair, "beta"].iloc[0]) * value for pair, value in weights.items() if not selected.loc[selected["pair"] == pair, "beta"].isna().all())
    if abs(beta) > policy.max_abs_beta and beta != 0:
        multiplier = policy.max_abs_beta / abs(beta)
        weights = {pair: value * multiplier for pair, value in weights.items()}
    return weights


def simulate_portfolio(features: pd.DataFrame, *, policy: PortfolioPolicy = PortfolioPolicy(), spot_only: bool = True, starting_balance: float = 1000.0) -> dict[str, Any]:
    if features.empty:
        return {"eligible": False, "reason": "no_point_in_time_membership_overlap"}
    timestamps = sorted(features["timestamp"].dropna().unique())
    previous: dict[str, float] = {}
    balance = float(starting_balance)
    equity = [balance]
    turnovers: list[float] = []
    for step, timestamp in enumerate(timestamps[:-1]):
        if step % max(1, policy.rebalance_every) == 0:
            current = features[features["timestamp"] == timestamp]
            weights = _weights(current, direction=1, policy=policy)
            if not spot_only:
                weights.update(_weights(current, direction=-1, policy=policy))
            turnover = sum(abs(weights.get(pair, 0.0) - previous.get(pair, 0.0)) for pair in set(weights) | set(previous))
            turnovers.append(turnover)
            balance *= max(0.0, 1.0 - turnover * (2.0 * policy.fee_bps + policy.spread_bps + policy.slippage_bps) / 10000.0)
            previous = weights
        next_timestamp = timestamps[step + 1]
        now = features[features["timestamp"] == timestamp].set_index("pair")
        nxt = features[features["timestamp"] == next_timestamp].set_index("pair")
        portfolio_return = 0.0
        for pair, weight in previous.items():
            if pair in now.index and pair in nxt.index:
                portfolio_return += weight * (float(nxt.loc[pair, "close"]) / float(now.loc[pair, "close"]) - 1.0)
        balance *= max(0.0, 1.0 + portfolio_return)
        equity.append(balance)
    curve = pd.Series(equity)
    drawdown = (curve / curve.cummax() - 1.0).min() * -100.0
    return {
        "eligible": True, "observations": len(timestamps), "rebalances": len(turnovers),
        "final_balance": balance, "profit_pct": (balance / starting_balance - 1.0) * 100.0,
        "max_drawdown_pct": float(drawdown), "mean_turnover": float(np.mean(turnovers)) if turnovers else 0.0,
        "policy": policy.__dict__, "spot_only": spot_only,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", type=Path, required=True)
    parser.add_argument("--membership", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    candles = pd.read_parquet(args.candles) if args.candles.suffix == ".parquet" else pd.read_feather(args.candles)
    membership = pd.read_parquet(args.membership) if args.membership.suffix == ".parquet" else pd.read_feather(args.membership)
    result = simulate_portfolio(build_features(candles, membership))
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
