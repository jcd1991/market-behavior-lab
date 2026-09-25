#!/usr/bin/env python3
"""Normalize venue minute trades or L2 snapshots into Parquet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.evaluation.microstructure import normalize_minute_trades, normalize_orderbook_snapshots


def read_frame(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".feather":
        return pd.read_feather(path)
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return pd.DataFrame(payload.get("data", payload) if isinstance(payload, (dict, list)) else [])
    return pd.read_csv(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("trades", "orderbook"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--pair", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--market-type", choices=("spot", "futures"), default="spot")
    args = parser.parse_args()
    frame = read_frame(args.input)
    if args.kind == "trades":
        normalized = normalize_minute_trades(frame, venue=args.venue, pair=args.pair, source=args.source, market_type=args.market_type)
    else:
        normalized = normalize_orderbook_snapshots(frame, venue=args.venue, pair=args.pair, source=args.source, market_type=args.market_type)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_parquet(args.output, index=False, compression=None)
    print(json.dumps({"schema_version": "microstructure.v1", "kind": args.kind, "rows": len(normalized), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
