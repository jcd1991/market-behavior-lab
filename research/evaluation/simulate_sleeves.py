#!/usr/bin/env python3
"""Simulate independently backtested sleeves under shared trade capacity.

Freqtrade runs each strategy export with its own wallet and position limit.
This evaluator rescales each sleeve to an explicit capital weight, merges its
entry/exit events, and rejects entries when a shared maximum-open-position
limit is reached. It remains a research approximation: it cannot recreate
intrabar order priority or portfolio-level signal generation.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Sleeve:
    name: str
    path: Path
    weight: float


@dataclass(frozen=True)
class Trade:
    sleeve: str
    pair: str
    open_date: pd.Timestamp
    close_date: pd.Timestamp
    profit_abs: float


def load_trades(path: Path, sleeve: str) -> list[Trade]:
    with zipfile.ZipFile(path) as archive:
        member = next(
            name for name in archive.namelist()
            if name.endswith(".json") and "config" not in name and not name.endswith("_meta.json")
        )
        payload = json.loads(archive.read(member))
    trades: list[Trade] = []
    for result in payload.get("strategy", {}).values():
        for row in result.get("trades", []) or []:
            opened = pd.to_datetime(row.get("open_date"), utc=True, errors="coerce")
            closed = pd.to_datetime(row.get("close_date"), utc=True, errors="coerce")
            if pd.isna(opened) or pd.isna(closed):
                continue
            trades.append(
                Trade(
                    sleeve=sleeve,
                    pair=str(row.get("pair", "")),
                    open_date=opened,
                    close_date=closed,
                    profit_abs=float(row.get("profit_abs", 0.0) or 0.0),
                )
            )
    return trades


def simulate(
    trades: list[Trade],
    weights: dict[str, float],
    *,
    starting_balance: float = 1000.0,
    source_balance: float = 1000.0,
    max_open_positions: int = 2,
) -> dict[str, Any]:
    if not trades:
        return {"starting_balance": starting_balance, "final_balance": starting_balance, "trades": 0, "skipped_trades": 0, "profit_abs": 0.0, "max_drawdown_abs": 0.0, "max_open_positions": 0}
    total_weight = sum(weights.values())
    if total_weight <= 0 or source_balance <= 0:
        raise ValueError("weights and source_balance must be positive")
    if max_open_positions < 1:
        raise ValueError("max_open_positions must be positive")

    ordered = sorted(trades, key=lambda trade: (trade.open_date, trade.close_date, trade.sleeve))
    active: list[Trade] = []
    accepted: list[tuple[pd.Timestamp, float, str]] = []
    skipped: dict[str, int] = {name: 0 for name in weights}
    accepted_counts: dict[str, int] = {name: 0 for name in weights}
    max_active = 0

    for trade in ordered:
        active = [item for item in active if item.close_date > trade.open_date]
        max_active = max(max_active, len(active))
        if len(active) >= max_open_positions:
            skipped[trade.sleeve] = skipped.get(trade.sleeve, 0) + 1
            continue
        active.append(trade)
        max_active = max(max_active, len(active))
        scale = (weights.get(trade.sleeve, 0.0) / total_weight) * (starting_balance / source_balance)
        accepted.append((trade.close_date, trade.profit_abs * scale, trade.sleeve))
        accepted_counts[trade.sleeve] = accepted_counts.get(trade.sleeve, 0) + 1

    equity = starting_balance
    peak = equity
    max_drawdown = 0.0
    for _, pnl, _ in sorted(accepted, key=lambda item: item[0]):
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    per_sleeve = {}
    for name, weight in weights.items():
        pnl = sum(pnl for _, pnl, sleeve in accepted if sleeve == name)
        per_sleeve[name] = {"weight": weight, "accepted_trades": accepted_counts.get(name, 0), "skipped_trades": skipped.get(name, 0), "profit_abs": pnl}
    return {
        "starting_balance": starting_balance,
        "final_balance": equity,
        "profit_abs": equity - starting_balance,
        "profit_pct": (equity - starting_balance) / starting_balance * 100.0,
        "trades": len(accepted),
        "skipped_trades": sum(skipped.values()),
        "max_open_positions_observed": max_active,
        "max_drawdown_abs": max_drawdown,
        "max_open_positions_limit": max_open_positions,
        "sleeves": per_sleeve,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--starting-balance", type=float, default=1000.0)
    parser.add_argument("--source-balance", type=float, default=1000.0)
    parser.add_argument("--max-open-positions", type=int, default=2)
    parser.add_argument("--sleeve", action="append", required=True, help="name:weight:path-to-freqtrade-zip")
    args = parser.parse_args()
    sleeves: list[Sleeve] = []
    for value in args.sleeve:
        name, weight, path = value.split(":", 2)
        sleeves.append(Sleeve(name=name, weight=float(weight), path=Path(path)))
    weights = {sleeve.name: sleeve.weight for sleeve in sleeves}
    trades = [trade for sleeve in sleeves for trade in load_trades(sleeve.path, sleeve.name)]
    print(json.dumps(simulate(trades, weights, starting_balance=args.starting_balance, source_balance=args.source_balance, max_open_positions=args.max_open_positions), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
