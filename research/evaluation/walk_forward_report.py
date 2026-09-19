#!/usr/bin/env python3
"""Summarize labeled Freqtrade walk-forward exports with bootstrap intervals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bootstrap_trades import bootstrap, load_trades


def summarize_runs(
    runs: list[tuple[str, Path]],
    *,
    strategy: str,
    iterations: int = 10000,
    seed: int = 1337,
    starting_balance: float = 1000.0,
) -> list[dict[str, Any]]:
    summaries = []
    for label, path in runs:
        trades = load_trades(path, strategy)
        pnls = [float(trade.get("profit_abs", 0.0) or 0.0) for trade in trades]
        result = bootstrap(
            pnls,
            starting_balance=starting_balance,
            iterations=iterations,
            seed=seed,
        )
        summaries.append(
            {
                "label": label,
                "input": str(path),
                "n_trades": result["n_trades"],
                "observed": result["observed"],
                "profit_interval": result["bootstrap_intervals"]["profit_pct"],
                "profitable_resamples_pct": result["profitable_resamples_pct"],
            }
        )
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="RegimeRouted")
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--starting-balance", type=float, default=1000.0)
    parser.add_argument("--run", action="append", required=True, help="label:path-to-freqtrade-zip")
    args = parser.parse_args()
    runs = []
    for value in args.run:
        label, path = value.split(":", 1)
        runs.append((label, Path(path)))
    print(json.dumps(summarize_runs(runs, strategy=args.strategy, iterations=args.iterations, seed=args.seed, starting_balance=args.starting_balance), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
