"""Apply additional per-trade execution costs to a Freqtrade export."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any


def load_trades(path: Path, strategy: str) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".json") and "config" not in name)
        payload = json.loads(archive.read(member))
    return list(payload.get("strategy", {}).get(strategy, {}).get("trades", []) or [])


def notional(trade: dict[str, Any]) -> float:
    amount = float(trade.get("amount", 0.0) or 0.0)
    open_rate = float(trade.get("open_rate", 0.0) or 0.0)
    stake = float(trade.get("stake_amount", 0.0) or 0.0)
    return max(stake, amount * open_rate)


def sensitivity(trades: list[dict[str, Any]], starting_balance: float, costs_bps: list[float]) -> list[dict[str, float]]:
    output = []
    for bps in costs_bps:
        pnls = [float(t.get("profit_abs", 0.0) or 0.0) - notional(t) * float(bps) / 10000.0 for t in trades]
        gross_wins = sum(x for x in pnls if x > 0)
        gross_losses = abs(sum(x for x in pnls if x < 0))
        profit = sum(pnls)
        output.append(
            {
                "additional_roundtrip_cost_bps": float(bps),
                "trades": float(len(pnls)),
                "profit_abs": float(profit),
                "profit_pct": float(profit / starting_balance * 100.0),
                "profit_factor": float(gross_wins / gross_losses) if gross_losses else float("inf"),
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--strategy", default="RegimeRouted")
    parser.add_argument("--starting-balance", type=float, default=1000.0)
    parser.add_argument("--cost-bps", nargs="+", type=float, default=[0.0, 5.0, 10.0, 20.0, 40.0])
    args = parser.parse_args()
    trades = load_trades(args.input, args.strategy)
    print(json.dumps(sensitivity(trades, args.starting_balance, args.cost_bps), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
