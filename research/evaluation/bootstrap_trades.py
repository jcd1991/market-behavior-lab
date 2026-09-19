#!/usr/bin/env python3
"""Bootstrap trade outcomes to quantify uncertainty in a backtest result.

This is deliberately different from ``monte_carlo_trades.py``: bootstrap
resampling changes the observed trade sample and estimates uncertainty in the
trade-level result. It is not a substitute for out-of-sample validation,
venue-specific costs, or a synchronized portfolio simulation.
"""

from __future__ import annotations

import argparse
import json
import random
import zipfile
from pathlib import Path
from typing import Any


def _float(value: Any) -> float:
    try:
        result = float(value)
        return result if result == result else 0.0
    except (TypeError, ValueError):
        return 0.0


def load_trades(path: Path, strategy: str) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            member = next(
                name
                for name in archive.namelist()
                if name.endswith(".json")
                and "config" not in name
                and not name.endswith("_meta.json")
            )
            payload = json.loads(archive.read(member))
    else:
        payload = json.loads(path.read_text())

    if isinstance(payload.get("strategy"), dict):
        return list(payload["strategy"].get(strategy, {}).get("trades", []) or [])
    return list(payload.get("trades", []) or [])


def _stats(pnls: list[float], starting_balance: float) -> dict[str, float]:
    equity = float(starting_balance)
    peak = equity
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    wins = sum(1 for pnl in pnls if pnl > 0)
    return {
        "profit_abs": equity - starting_balance,
        "profit_pct": (equity - starting_balance) / starting_balance * 100.0,
        "max_drawdown_abs": max_dd,
        "win_rate_pct": wins / len(pnls) * 100.0 if pnls else 0.0,
    }


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * max(0.0, min(1.0, q))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def bootstrap(
    pnls: list[float],
    *,
    starting_balance: float,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    if not pnls:
        raise ValueError("at least one trade is required")
    rng = random.Random(seed)
    samples = {key: [] for key in ("profit_abs", "profit_pct", "max_drawdown_abs", "win_rate_pct")}
    for _ in range(max(1, iterations)):
        sample = [pnls[rng.randrange(len(pnls))] for _ in pnls]
        stats = _stats(sample, starting_balance)
        for key, value in stats.items():
            samples[key].append(value)

    observed = _stats(pnls, starting_balance)
    intervals = {
        key: {
            "p05": _quantile(values, 0.05),
            "p50": _quantile(values, 0.50),
            "p95": _quantile(values, 0.95),
        }
        for key, values in samples.items()
    }
    profitable = sum(value > 0 for value in samples["profit_abs"])
    return {
        "n_trades": len(pnls),
        "iterations": max(1, iterations),
        "seed": seed,
        "starting_balance": starting_balance,
        "observed": observed,
        "bootstrap_intervals": intervals,
        "profitable_resamples_pct": profitable / max(1, iterations) * 100.0,
        "note": (
            "IID trade bootstrap estimates uncertainty from the observed trade "
            "sample. It does not establish future profitability or account for "
            "parameter selection and market-regime drift."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--strategy", default="RegimeRouted")
    parser.add_argument("--starting-balance", type=float, default=1000.0)
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    trades = load_trades(args.input, args.strategy)
    pnls = [_float(trade.get("profit_abs")) for trade in trades]
    result = bootstrap(
        pnls,
        starting_balance=args.starting_balance,
        iterations=args.iterations,
        seed=args.seed,
    )
    result["input"] = str(args.input.resolve())
    result["strategy"] = args.strategy
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
