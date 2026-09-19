"""Summarize comparable Freqtrade exports across native timeframes."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any


def load_trades(path: str | Path, strategy: str | None = None) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix == ".zip":
        with zipfile.ZipFile(source) as archive:
            names = [name for name in archive.namelist() if name.endswith(".json")]
            if not names:
                raise ValueError(f"no JSON export in {source}")
            payload = json.loads(archive.read(names[0]))
    else:
        payload = json.loads(source.read_text())
    trades = payload.get("strategy", {}).get(strategy, {}).get("trades") if strategy else None
    if trades is None:
        trades = payload.get("trades", payload if isinstance(payload, list) else [])
    return [trade for trade in trades if isinstance(trade, dict)]


def summarize(trades: list[dict[str, Any]], starting_balance: float = 1000.0) -> dict[str, Any]:
    profits = [float(t.get("profit_abs", t.get("profit_abs_pct", 0.0))) for t in trades]
    wins = [profit for profit in profits if profit > 0]
    losses = [profit for profit in profits if profit < 0]
    equity = float(starting_balance)
    peak = equity
    max_drawdown = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    gross_loss = abs(sum(losses))
    return {
        "trades": len(profits),
        "profit_abs": round(sum(profits), 8),
        "return_pct": round(sum(profits) / starting_balance * 100, 8) if starting_balance else None,
        "win_rate": round(len(wins) / len(profits), 8) if profits else None,
        "profit_factor": round(sum(wins) / gross_loss, 8) if gross_loss else None,
        "max_drawdown": round(max_drawdown, 8),
    }


def compare(inputs: list[tuple[str, str | Path]], strategy: str | None = None, starting_balance: float = 1000.0) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "starting_balance": starting_balance,
        "runs": [{"label": label, **summarize(load_trades(path, strategy), starting_balance)} for label, path in inputs],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy")
    parser.add_argument("--starting-balance", type=float, default=1000.0)
    parser.add_argument("--run", action="append", required=True, metavar="LABEL=PATH")
    args = parser.parse_args()
    inputs = []
    for item in args.run:
        label, separator, path = item.partition("=")
        if not separator or not label or not path:
            parser.error("--run must be LABEL=PATH")
        inputs.append((label, path))
    print(json.dumps(compare(inputs, args.strategy, args.starting_balance), indent=2))


if __name__ == "__main__":
    main()
