#!/usr/bin/env python3
"""Combine Binance daily derivatives-metrics archives into one UTC Feather panel.

The public metrics archive is daily, not minute-level.  This helper keeps that
resolution explicit while preserving the official archive provenance and the
same venue/pair contract used by the derivative normalizer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

# Make the repository-root package import work when this file is invoked as a
# script, which is the documented workflow for the data tools.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.normalize_binance_derivatives import normalize


def normalize_series(
    inputs: list[Path], *, pair: str, source: str
) -> tuple[pd.DataFrame, dict[str, object]]:
    if not inputs:
        raise ValueError("no Binance metrics archives found")
    frames: list[pd.DataFrame] = []
    conventions: list[str] = []
    for path in sorted(inputs):
        frame, manifest = normalize(path, kind="metrics", pair=pair, source=source)
        frames.append(frame)
        conventions.append(str(manifest.get("metrics_label_convention", "ambiguous")))
    combined = pd.concat(frames, ignore_index=True).sort_values(["date", "available_at"])
    if combined["available_at"].notna().all():
        combined = combined.drop_duplicates("available_at", keep="last")
    combined = combined.reset_index(drop=True)
    if combined.empty:
        raise ValueError("metrics archives contained no valid rows")
    columns = list(combined.columns)
    manifest = {
        "schema_version": "normalized-derivatives.v1",
        "venue": "binance-global",
        "kind": "metrics",
        "frequency": "5m",
        "pair": pair,
        "source": source,
        "execution_truth": False,
        "inputs": [str(path) for path in sorted(inputs)],
        "input_count": len(inputs),
        "rows": int(len(combined)),
        "start": str(combined.iloc[0]["date"]),
        "end": str(combined.iloc[-1]["date"]),
        "columns": columns,
        "timestamps": "UTC",
        "venue_mixing": "forbidden",
        "metrics_label_conventions": sorted(set(conventions)),
        "point_in_time_status": (
            "safe"
            if combined.get("available_at", pd.Series(dtype=object)).notna().all()
            else "ambiguous"
        ),
        "availability_rule": "end_labeled=label; start_labeled=label+5m; ambiguous=NaT",
    }
    return combined[columns], manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--pair", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    symbol = args.symbol.upper()
    inputs = sorted(args.input_dir.glob(f"um-{symbol}-metrics-*.zip"))
    frame, manifest = normalize_series(inputs, pair=args.pair, source=args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_feather(args.output)
    args.output.with_suffix(args.output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
