"""Small, locked-window grid search for the two-leg cointegration book."""

from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path

try:
    from .cointegration_book import load_ohlcv, simulate_pair
except ImportError:  # pragma: no cover - direct CLI execution
    from cointegration_book import load_ohlcv, simulate_pair


def tune_pair(
    asset_path: Path,
    reference_path: Path,
    *,
    venue: str,
    train_start: str,
    train_end: str,
    round_trip_cost: float = 0.002,
) -> dict:
    asset = load_ohlcv(asset_path).loc[train_start:train_end]
    reference = load_ohlcv(reference_path).loc[train_start:train_end]
    rows = []
    for window, entry_z, exit_z, min_corr, max_half_life in product(
        (168, 240), (1.6, 1.8, 2.0), (0.25, 0.35), (0.70, 0.80), (96.0, 120.0)
    ):
        result = simulate_pair(
            asset,
            reference,
            venue=venue,
            window=window,
            entry_z=entry_z,
            exit_z=exit_z,
            min_corr=min_corr,
            max_half_life=max_half_life,
            round_trip_cost=round_trip_cost,
        )
        if result.get("eligible") and result.get("entries", 0) >= 5:
            result["score"] = float(result["profit_ratio"] - 1.5 * result["max_drawdown_pct"] / 100.0)
            rows.append(result)
    rows.sort(key=lambda row: (row["score"], row["profit_ratio"]), reverse=True)
    return {
        "venue": venue,
        "train_start": train_start,
        "train_end": train_end,
        "round_trip_cost": round_trip_cost,
        "tested": len(rows),
        "best": rows[0] if rows else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--train-start", default="2024-06-01")
    parser.add_argument("--train-end", default="2025-01-01")
    parser.add_argument("--round-trip-cost", type=float, default=0.002)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = tune_pair(
        args.asset,
        args.reference,
        venue=args.venue,
        train_start=args.train_start,
        train_end=args.train_end,
        round_trip_cost=args.round_trip_cost,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
