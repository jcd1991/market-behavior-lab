"""Frozen-sleeve ensemble evaluator with shared capital and cost controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SleeveSpec:
    name: str
    weight: float
    max_pair_fraction: float = 0.25


def evaluate_frozen_sleeves(
    trades: pd.DataFrame,
    sleeves: tuple[SleeveSpec, ...],
    *,
    starting_balance: float = 1000.0,
    max_open_positions: int = 3,
    fee_bps: float = 10.0,
    spread_bps: float = 5.0,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Evaluate separate strategy sleeves without retuning or averaging PnL.

    The input must contain one row per closed trade.  Signals are accepted in
    timestamp order, not by best historical return, and overlapping pairs are
    rejected.  This makes the result a portfolio-capacity screen rather than a
    cherry-picked matrix average.
    """
    required = {"sleeve", "pair", "open_time", "close_time", "profit_ratio"}
    if not required.issubset(trades.columns):
        raise ValueError(f"trades missing columns: {sorted(required - set(trades.columns))}")
    weights = {spec.name: float(spec.weight) for spec in sleeves if spec.weight > 0}
    if not weights:
        raise ValueError("at least one positive sleeve weight is required")
    total = sum(weights.values())
    frame = trades.copy()
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True, errors="coerce")
    frame["close_time"] = pd.to_datetime(frame["close_time"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["open_time", "close_time"]).sort_values(["open_time", "close_time", "sleeve", "pair"])
    active: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    balance = float(starting_balance)
    cost = (2.0 * fee_bps + spread_bps + slippage_bps) / 10000.0
    spec_map = {spec.name: spec for spec in sleeves}
    for _, row in frame.iterrows():
        now = row["open_time"]
        closed = [position for position in active if position["close_time"] <= now]
        active = [position for position in active if position["close_time"] > now]
        for position in closed:
            balance += position["stake"] * (position["profit_ratio"] - cost)
            accepted.append(position)
        if len(active) >= max_open_positions:
            rejected["max_open_positions"] = rejected.get("max_open_positions", 0) + 1
            continue
        if any(position["pair"] == row["pair"] for position in active):
            rejected["pair_overlap"] = rejected.get("pair_overlap", 0) + 1
            continue
        spec = spec_map.get(str(row["sleeve"]))
        if spec is None:
            rejected["unknown_sleeve"] = rejected.get("unknown_sleeve", 0) + 1
            continue
        budget = balance * spec.weight / total
        stake = min(budget / max_open_positions, balance * spec.max_pair_fraction)
        if stake <= 0:
            rejected["zero_stake"] = rejected.get("zero_stake", 0) + 1
            continue
        active.append({"sleeve": str(row["sleeve"]), "pair": str(row["pair"]), "open_time": row["open_time"], "close_time": row["close_time"], "stake": stake, "profit_ratio": float(row["profit_ratio"]), "cost_ratio": cost})
    for position in active:
        balance += position["stake"] * (position["profit_ratio"] - cost)
        accepted.append({**position, "force_closed": True})
    by_sleeve: dict[str, dict[str, Any]] = {}
    for name in weights:
        rows = [row for row in accepted if row["sleeve"] == name]
        by_sleeve[name] = {"weight": weights[name] / total, "accepted": len(rows), "profit_abs": sum(row["stake"] * (row["profit_ratio"] - cost) for row in rows)}
    return {
        "schema_version": "frozen-ensemble.v1", "starting_balance": starting_balance,
        "final_balance": balance, "profit_abs": balance - starting_balance,
        "profit_pct": (balance / starting_balance - 1.0) * 100.0,
        "accepted": len(accepted), "rejected": sum(rejected.values()), "rejections": rejected,
        "cost_model": {"fee_bps_per_side": fee_bps, "spread_bps_round_trip": spread_bps, "slippage_bps_round_trip": slippage_bps},
        "sleeves": by_sleeve,
    }


def sleeve_return_panel(trades: pd.DataFrame) -> pd.DataFrame:
    """Create a non-overlapping close-time return panel for correlation review."""
    if trades.empty:
        return pd.DataFrame(columns=["timestamp", "sleeve", "return"])
    out = trades.copy()
    out["timestamp"] = pd.to_datetime(out["close_time"], utc=True, errors="coerce")
    out["return"] = pd.to_numeric(out["profit_ratio"], errors="coerce")
    return out.dropna(subset=["timestamp", "return"])[["timestamp", "sleeve", "return"]].sort_values("timestamp")
