#!/usr/bin/env python3
"""Normalize one OKX public derivative JSON response into a Feather file.

This keeps derivative observations separate from candles so a missing feature
stays missing. It supports funding history, mark price, index candles, and
open interest. The sidecar records the OKX instrument and source label; it
does not claim that a bounded API page is a complete execution history.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _rows(path: Path) -> list:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("code") not in {None, "0", 0}:
        raise ValueError(f"OKX response failed: {payload.get('code')} {payload.get('msg')}")
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"OKX response has no data rows: {path}")
    return rows


def normalize(path: Path, *, kind: str) -> pd.DataFrame:
    rows = _rows(path)
    if kind == "funding":
        frame = pd.DataFrame({
            "date": [row.get("fundingTime") for row in rows],
            "funding_rate": [row.get("fundingRate", row.get("realizedRate")) for row in rows],
            "instrument": [row.get("instId") for row in rows],
        })
    elif kind == "mark":
        frame = pd.DataFrame({
            "date": [row.get("ts") for row in rows],
            "mark_price": [row.get("markPx") for row in rows],
            "instrument": [row.get("instId") for row in rows],
        })
    elif kind == "open-interest":
        frame = pd.DataFrame({
            "date": [row.get("ts") for row in rows],
            "open_interest": [row.get("oi") for row in rows],
            "open_interest_usd": [row.get("oiUsd") for row in rows],
            "instrument": [row.get("instId") for row in rows],
        })
    elif kind == "index-candles":
        if any(not isinstance(row, list) or len(row) < 5 for row in rows):
            raise ValueError("OKX index candles must be array rows")
        frame = pd.DataFrame({
            "date": [row[0] for row in rows],
            "index_open": [row[1] for row in rows],
            "index_high": [row[2] for row in rows],
            "index_low": [row[3] for row in rows],
            "index_close": [row[4] for row in rows],
        })
    else:
        raise ValueError(f"unsupported derivative kind: {kind}")
    frame["date"] = pd.to_datetime(pd.to_numeric(frame["date"], errors="coerce"), unit="ms", utc=True, errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date").reset_index(drop=True)
    for column in frame.columns:
        if column not in {"date", "instrument"}:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.empty:
        raise ValueError(f"no valid derivative timestamps in {path}")
    return frame


def write_normalized(input_path: Path, output: Path, *, kind: str, pair: str, source: str) -> dict[str, object]:
    frame = normalize(input_path, kind=kind)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_feather(output)
    manifest = {
        "schema_version": "normalized-derivatives.v1",
        "venue": "okx",
        "kind": kind,
        "pair": pair,
        "source": source,
        "execution_truth": False,
        "input": str(input_path),
        "rows": int(len(frame)),
        "start": str(frame.iloc[0]["date"]),
        "end": str(frame.iloc[-1]["date"]),
        "timestamps": "UTC",
        "venue_mixing": "forbidden",
    }
    output.with_suffix(output.suffix + ".manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("funding", "mark", "index-candles", "open-interest"), required=True)
    parser.add_argument("--pair", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    print(json.dumps(write_normalized(args.input, args.output, kind=args.kind, pair=args.pair, source=args.source), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
