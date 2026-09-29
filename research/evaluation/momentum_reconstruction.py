"""Causal, low-frequency screening evaluator for the reconstructed momentum lane.

The archived ``MomentumRegimeBasket15mLb30`` source is incomplete, so this
module is intentionally a research companion to the Freqtrade reconstruction,
not a claim that the old export has been reproduced.  It turns native candles
into daily, previous-close features and runs a frozen train/holdout grid with
explicit costs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MomentumPolicy:
    lookback_days: int = 30
    trend_days: int = 50
    regime_days: int = 100
    top_n: int = 3
    exit_rank: int = 15
    fee_bps: float = 10.0
    spread_bps: float = 5.0
    slippage_bps: float = 5.0
    max_pair_weight: float = 0.50


def _as_utc(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _daily_features(candles: pd.DataFrame, policy: MomentumPolicy) -> pd.DataFrame:
    required = {"timestamp", "pair", "close"}
    if not required.issubset(candles.columns):
        raise ValueError(f"candles missing columns: {sorted(required - set(candles.columns))}")
    frame = candles.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "pair", "close"]).sort_values(["pair", "timestamp"])
    frame["day"] = frame["timestamp"].dt.floor("D")
    daily = frame.groupby(["pair", "day"], as_index=False)["close"].last()
    rows: list[pd.DataFrame] = []
    for pair, local in daily.groupby("pair", sort=False):
        local = local.set_index("day").sort_index()
        previous = local["close"].shift(1)
        out = pd.DataFrame(index=local.index)
        out["pair"] = pair
        out["close"] = local["close"]
        out["momentum"] = previous.pct_change(policy.lookback_days)
        out["trend_ok"] = previous.gt(previous.rolling(policy.trend_days, min_periods=policy.trend_days).mean())
        rows.append(out.reset_index(names="timestamp"))
    features = pd.concat(rows, ignore_index=True)
    features["rank"] = features.groupby("timestamp")["momentum"].rank(ascending=False, method="min")
    btc = features[features["pair"].str.startswith("BTC/")].set_index("timestamp")["close"]
    btc_previous = btc.shift(1)
    regime = btc_previous.gt(btc_previous.rolling(policy.regime_days, min_periods=policy.regime_days).mean())
    features["regime_ok"] = features["timestamp"].map(regime).fillna(False)
    return features.sort_values(["timestamp", "pair"]).reset_index(drop=True)


def simulate(candles: pd.DataFrame, policy: MomentumPolicy, *, start: str | pd.Timestamp | None = None, end: str | pd.Timestamp | None = None, starting_balance: float = 1000.0) -> dict[str, Any]:
    features = _daily_features(candles, policy)
    if start is not None:
        features = features[features["timestamp"] >= _as_utc(start)]
    if end is not None:
        features = features[features["timestamp"] < _as_utc(end)]
    dates = sorted(features["timestamp"].unique())
    if len(dates) < 2:
        return {"eligible": False, "reason": "insufficient_daily_overlap", "policy": asdict(policy)}
    balance = float(starting_balance)
    previous: dict[str, float] = {}
    curve = [balance]
    turnover_values: list[float] = []
    for current, following in zip(dates[:-1], dates[1:]):
        rows = features[features["timestamp"] == current].dropna(subset=["momentum", "rank"])
        selected = rows[rows["regime_ok"] & rows["trend_ok"] & rows["rank"].le(policy.exit_rank)].sort_values("rank").head(policy.top_n)
        if selected.empty:
            weights: dict[str, float] = {}
        else:
            raw = min(policy.max_pair_weight, 1.0 / len(selected))
            weights = {str(pair): raw for pair in selected["pair"]}
        turnover = sum(abs(weights.get(pair, 0.0) - previous.get(pair, 0.0)) for pair in set(weights) | set(previous))
        turnover_values.append(turnover)
        balance *= max(0.0, 1.0 - turnover * (2.0 * policy.fee_bps + policy.spread_bps + policy.slippage_bps) / 10000.0)
        now = features[features["timestamp"] == current].set_index("pair")["close"]
        nxt = features[features["timestamp"] == following].set_index("pair")["close"]
        portfolio_return = sum(weight * (float(nxt[pair]) / float(now[pair]) - 1.0) for pair, weight in weights.items() if pair in now.index and pair in nxt.index)
        balance *= max(0.0, 1.0 + portfolio_return)
        previous = weights
        curve.append(balance)
    equity = pd.Series(curve)
    drawdown = float((equity / equity.cummax() - 1.0).min() * -100.0)
    return {"eligible": True, "observations": len(dates), "rebalances": len(turnover_values),
            "final_balance": balance, "profit_pct": (balance / starting_balance - 1.0) * 100.0,
            "max_drawdown_pct": drawdown, "mean_turnover": float(np.mean(turnover_values)) if turnover_values else 0.0,
            "policy": asdict(policy)}


def tune(candles: pd.DataFrame, *, train_end: str, holdout_start: str, grid: list[MomentumPolicy] | None = None) -> dict[str, Any]:
    """Tune only on the train window and evaluate the selected policy once."""
    policies = grid or [
        MomentumPolicy(lookback_days=14, trend_days=30, regime_days=60, top_n=2, exit_rank=9),
        MomentumPolicy(lookback_days=30, trend_days=50, regime_days=100, top_n=3, exit_rank=15),
        MomentumPolicy(lookback_days=60, trend_days=75, regime_days=120, top_n=3, exit_rank=15),
        MomentumPolicy(lookback_days=90, trend_days=100, regime_days=150, top_n=2, exit_rank=9),
    ]
    candidates = []
    for policy in policies:
        train = simulate(candles, policy, end=train_end)
        score = float(train.get("profit_pct", -np.inf)) - 0.5 * float(train.get("max_drawdown_pct", 100.0)) if train.get("eligible") else -np.inf
        candidates.append({"policy": asdict(policy), "train": train, "score": score})
    selected = max(candidates, key=lambda item: item["score"])
    policy = MomentumPolicy(**selected["policy"])
    holdout = simulate(candles, policy, start=holdout_start)
    return {"selected": selected["policy"], "selection_rule": "train profit minus 0.5x drawdown; frozen holdout",
            "candidates": candidates, "holdout": holdout}
