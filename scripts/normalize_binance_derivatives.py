#!/usr/bin/env python3
"""Normalize Binance public index, mark, and funding archives.

The output remains explicitly non-execution-truth.  It is suitable for
coverage checks and same-venue research only when spot, perpetual, index, and
funding manifests overlap and carry the same Binance market label.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import zipfile

import pandas as pd


def _csv_bytes(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv") and not name.endswith("/")]
        if len(members) != 1:
            raise ValueError(f"expected one CSV member in {path}, found {members}")
        return archive.read(members[0])


def _utc_timestamp(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return pd.to_datetime(numeric, unit="ms", utc=True, errors="coerce")


def normalize(path: Path, *, kind: str, pair: str, source: str) -> tuple[pd.DataFrame, dict[str, object]]:
    raw = pd.read_csv(BytesIO(_csv_bytes(path)))
    if kind in {"indexPriceKlines", "markPriceKlines"}:
        required = {"open_time", "open", "high", "low", "close"}
        missing = sorted(required - set(raw.columns))
        if missing:
            raise ValueError(f"missing kline columns: {missing}")
        frame = raw[["open_time", "open", "high", "low", "close"]].copy()
        frame["date"] = _utc_timestamp(frame.pop("open_time"))
        prefix = "index" if kind == "indexPriceKlines" else "mark"
        frame = frame.rename(columns={column: f"{prefix}_{column}" for column in ("open", "high", "low", "close")})
        output_columns = ["date", f"{prefix}_open", f"{prefix}_high", f"{prefix}_low", f"{prefix}_close"]
    elif kind == "fundingRate":
        required = {"calc_time", "funding_interval_hours", "last_funding_rate"}
        missing = sorted(required - set(raw.columns))
        if missing:
            raise ValueError(f"missing funding columns: {missing}")
        frame = raw[["calc_time", "funding_interval_hours", "last_funding_rate"]].copy()
        frame["date"] = _utc_timestamp(frame.pop("calc_time"))
        frame = frame.rename(columns={"last_funding_rate": "funding_rate"})
        output_columns = ["date", "funding_interval_hours", "funding_rate"]
    else:
        raise ValueError(f"unsupported Binance derivative kind: {kind}")
    for column in output_columns:
        if column != "date":
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=output_columns).sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if frame.empty:
        raise ValueError(f"no valid rows in {path}")
    manifest = {
        "schema_version": "normalized-derivatives.v1",
        "venue": "binance-global",
        "kind": kind,
        "pair": pair,
        "source": source,
        "execution_truth": False,
        "input": str(path),
        "rows": int(len(frame)),
        "start": str(frame.iloc[0]["date"]),
        "end": str(frame.iloc[-1]["date"]),
        "columns": output_columns,
        "timestamps": "UTC",
        "venue_mixing": "forbidden",
    }
    return frame[output_columns], manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("indexPriceKlines", "markPriceKlines", "fundingRate"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pair", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    frame, manifest = normalize(args.input, kind=args.kind, pair=args.pair, source=args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_feather(args.output)
    args.output.with_suffix(args.output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
