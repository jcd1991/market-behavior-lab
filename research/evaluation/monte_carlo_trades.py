#!/usr/bin/env python3
"""
Trade-order Monte Carlo for freqtrade backtest exports.

This script keeps trade outcomes fixed and permutes order to estimate path risk:
- max drawdown distribution
- longest losing streak distribution

Usage:
  python research/evaluation/monte_carlo_trades.py \
      --input /tmp/backtest_export.json \
      --output /tmp/monte_carlo_example.json \
      --permutations 10000
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import zipfile
from pathlib import Path
from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if out != out:  # NaN guard
            return default
        return out
    except Exception:
        return default


def _q(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    q = max(0.0, min(1.0, float(quantile)))
    idx = int(round((len(sorted_values) - 1) * q))
    return float(sorted_values[idx])


def sequence_path_stats(pnls_abs: list[float], starting_equity: float) -> dict[str, float]:
    equity = float(starting_equity)
    peak = equity
    max_dd_abs = 0.0
    max_dd_pct = 0.0
    losing_streak = 0
    max_losing_streak = 0

    for pnl in pnls_abs:
        equity += float(pnl)
        if equity > peak:
            peak = equity
        dd_abs_now = max(0.0, peak - equity)
        dd_pct_now = (dd_abs_now / peak * 100.0) if peak > 0 else 0.0
        if dd_abs_now > max_dd_abs:
            max_dd_abs = dd_abs_now
        if dd_pct_now > max_dd_pct:
            max_dd_pct = dd_pct_now

        if pnl < 0:
            losing_streak += 1
            if losing_streak > max_losing_streak:
                max_losing_streak = losing_streak
        else:
            losing_streak = 0

    return {
        "final_equity": float(equity),
        "total_pnl_abs": float(equity - starting_equity),
        "max_dd_abs": float(max_dd_abs),
        "max_dd_pct": float(max_dd_pct),
        "max_losing_streak": float(max_losing_streak),
    }


def monte_carlo_from_pnls(
    pnls_abs: list[float],
    *,
    starting_equity: float,
    permutations: int = 10000,
    seed: int = 1337,
) -> dict[str, Any]:
    rng = random.Random(int(seed))
    n_perm = max(1, int(permutations))
    seq = [float(x) for x in pnls_abs]

    max_dd_pcts: list[float] = []
    max_dd_abss: list[float] = []
    losing_streaks: list[float] = []
    final_equities: list[float] = []

    for _ in range(n_perm):
        shuffled = list(seq)
        rng.shuffle(shuffled)
        stats = sequence_path_stats(shuffled, starting_equity)
        max_dd_pcts.append(float(stats["max_dd_pct"]))
        max_dd_abss.append(float(stats["max_dd_abs"]))
        losing_streaks.append(float(stats["max_losing_streak"]))
        final_equities.append(float(stats["final_equity"]))

    max_dd_pcts.sort()
    max_dd_abss.sort()
    losing_streaks.sort()
    final_equities.sort()

    profitable_paths = sum(1 for x in final_equities if x > float(starting_equity))
    base = sequence_path_stats(seq, starting_equity)
    gross_win_abs = sum(x for x in seq if x > 0)
    gross_loss_abs = abs(sum(x for x in seq if x < 0))

    return {
        "n_trades": len(seq),
        "permutations": n_perm,
        "seed": int(seed),
        "start_equity": float(starting_equity),
        "fixed_total_pnl_abs": float(sum(seq)),
        "base_order": base,
        "gross_win_abs": float(gross_win_abs),
        "gross_loss_abs": float(gross_loss_abs),
        "profit_factor_from_trades": float(gross_win_abs / gross_loss_abs) if gross_loss_abs > 0 else None,
        "p50_max_dd_pct": float(_q(max_dd_pcts, 0.50)),
        "p95_max_dd_pct": float(_q(max_dd_pcts, 0.95)),
        "p99_max_dd_pct": float(_q(max_dd_pcts, 0.99)),
        "p50_max_dd_abs": float(_q(max_dd_abss, 0.50)),
        "p95_max_dd_abs": float(_q(max_dd_abss, 0.95)),
        "p99_max_dd_abs": float(_q(max_dd_abss, 0.99)),
        "p50_losing_streak": int(round(_q(losing_streaks, 0.50))),
        "p95_losing_streak": int(round(_q(losing_streaks, 0.95))),
        "p99_losing_streak": int(round(_q(losing_streaks, 0.99))),
        "profitable_paths_pct": float(100.0 * profitable_paths / n_perm),
        "note": (
            "Trade-order Monte Carlo keeps outcomes fixed and changes ordering only. "
            "Use this for path-risk sensitivity (drawdown / streak risk), not edge discovery."
        ),
    }


def _extract_trades_from_result_payload(payload: dict[str, Any], strategy: str | None = None) -> list[dict[str, Any]]:
    if "strategy" in payload and isinstance(payload["strategy"], dict):
        if strategy and strategy in payload["strategy"]:
            return list(payload["strategy"][strategy].get("trades", []) or [])
        if payload["strategy"]:
            first = next(iter(payload["strategy"].values()))
            if isinstance(first, dict):
                return list(first.get("trades", []) or [])
    if "trades" in payload and isinstance(payload["trades"], list):
        return list(payload["trades"])
    if "data" in payload and isinstance(payload["data"], list):
        return list(payload["data"])
    return []


def load_trades(path: Path, strategy: str | None = None) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            json_members = [
                n
                for n in zf.namelist()
                if n.endswith(".json") and "_config" not in n and not n.endswith("_meta.json")
            ]
            if not json_members:
                raise RuntimeError(f"No usable JSON payload in zip: {path}")
            payload = json.loads(zf.read(json_members[0]))
        return _extract_trades_from_result_payload(payload, strategy=strategy)

    if path.suffix.lower() == ".csv":
        rows: list[dict[str, Any]] = []
        with path.open("r", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(dict(row))
        return rows

    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict):
        return _extract_trades_from_result_payload(payload, strategy=strategy)
    return []


def trade_pnls_abs(trades: list[dict[str, Any]]) -> list[float]:
    pnls: list[float] = []
    for t in trades:
        if "profit_abs" in t:
            pnls.append(_to_float(t.get("profit_abs"), 0.0))
            continue

        profit_ratio = _to_float(t.get("profit_ratio", t.get("profit_pct", 0.0)), 0.0)
        stake = _to_float(t.get("stake_amount", t.get("amount", 0.0)), 0.0)
        pnls.append(float(profit_ratio * stake))
    return pnls


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to trades JSON/CSV or backtest result zip.")
    ap.add_argument("--output", default="/tmp/monte_carlo_trades.json")
    ap.add_argument("--strategy", default="RegimeRouted")
    ap.add_argument("--permutations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--starting-equity", type=float, default=1000.0)
    args = ap.parse_args()

    in_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()

    trades = load_trades(in_path, strategy=args.strategy)
    pnls_abs = trade_pnls_abs(trades)
    result = monte_carlo_from_pnls(
        pnls_abs,
        starting_equity=float(args.starting_equity),
        permutations=int(args.permutations),
        seed=int(args.seed),
    )
    result["input_path"] = str(in_path)
    result["output_path"] = str(out_path)
    result["strategy"] = args.strategy

    out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
