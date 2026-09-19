"""Combine independent Freqtrade trade exports into a sleeve portfolio.

This is an approximation: each input run has its own wallet and execution
constraints. It is useful for ranking sleeve diversification, not for proving
that a single Freqtrade bot could execute the combined book without a
synchronized multi-strategy allocator.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Sleeve:
    name: str
    path: Path
    weight: float


def load_trades(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        json_name = next(name for name in archive.namelist() if name.endswith(".json") and "config" not in name)
        payload = json.loads(archive.read(json_name))
    strategies = payload.get("strategy", {})
    rows = []
    for strategy_name, result in strategies.items():
        for trade in result.get("trades", []):
            rows.append(
                {
                    "strategy": strategy_name,
                    "close_date": trade.get("close_date"),
                    "profit_abs": float(trade.get("profit_abs", 0.0) or 0.0),
                    "pair": trade.get("pair", ""),
                }
            )
    return pd.DataFrame(rows)


def combine(sleeves: list[Sleeve], starting_balance: float) -> dict:
    if not sleeves:
        raise ValueError("at least one sleeve is required")
    total_weight = sum(sleeve.weight for sleeve in sleeves)
    if total_weight <= 0:
        raise ValueError("sleeve weights must sum to a positive value")
    events = []
    details = []
    for sleeve in sleeves:
        trades = load_trades(sleeve.path)
        if trades.empty:
            continue
        trades["close_date"] = pd.to_datetime(trades["close_date"], utc=True, errors="coerce")
        trades = trades.dropna(subset=["close_date"])
        trades["weighted_profit_abs"] = trades["profit_abs"] * sleeve.weight / total_weight
        trades["sleeve"] = sleeve.name
        events.append(trades[["close_date", "weighted_profit_abs", "sleeve", "pair"]])
        details.append({"sleeve": sleeve.name, "weight": sleeve.weight, "trades": len(trades), "profit_abs": float(trades["weighted_profit_abs"].sum())})
    if not events:
        return {"starting_balance": starting_balance, "final_balance": starting_balance, "profit_abs": 0.0, "profit_pct": 0.0, "trades": 0, "max_drawdown_abs": 0.0, "sleeves": details}
    frame = pd.concat(events, ignore_index=True).sort_values("close_date")
    equity = starting_balance + frame["weighted_profit_abs"].cumsum()
    drawdown = equity - equity.cummax()
    profit = float(frame["weighted_profit_abs"].sum())
    return {
        "starting_balance": starting_balance,
        "final_balance": starting_balance + profit,
        "profit_abs": profit,
        "profit_pct": profit / starting_balance * 100.0,
        "trades": int(len(frame)),
        "max_drawdown_abs": float(abs(drawdown.min())),
        "sleeves": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--starting-balance", type=float, default=1000.0)
    parser.add_argument("--sleeve", action="append", required=True, help="name:weight:path-to-freqtrade-zip")
    args = parser.parse_args()
    sleeves = []
    for value in args.sleeve:
        name, weight, path = value.split(":", 2)
        sleeves.append(Sleeve(name=name, weight=float(weight), path=Path(path)))
    print(json.dumps(combine(sleeves, args.starting_balance), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
