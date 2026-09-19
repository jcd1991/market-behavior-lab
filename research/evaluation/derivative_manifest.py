"""Validate derivative files before they are used in a research lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REQUIRED = ("funding_rate", "mark", "index", "open_interest")


def _kind(path: Path) -> str:
    lower = path.name.lower()
    if "funding_rate" in lower:
        return "funding_rate"
    if "open_interest" in lower or "openinterest" in lower:
        return "open_interest"
    if "index" in lower:
        return "index"
    if "mark" in lower:
        return "mark"
    return "ohlcv"


def _audit_file(path: Path, ohlcv_range: tuple[pd.Timestamp, pd.Timestamp] | None) -> dict:
    frame = pd.read_feather(path)
    dates = pd.to_datetime(frame.get("date"), utc=True, errors="coerce")
    valid = dates.dropna().sort_values()
    result = {
        "file": str(path),
        "kind": _kind(path),
        "rows": int(len(frame)),
        "date_min": valid.min().isoformat() if not valid.empty else None,
        "date_max": valid.max().isoformat() if not valid.empty else None,
        "has_date": bool(not valid.empty),
        "columns": list(frame.columns),
        "overlap_rows": 0,
        "status": "empty" if valid.empty else "usable",
    }
    if ohlcv_range and not valid.empty:
        start, end = ohlcv_range
        result["overlap_rows"] = int(((valid >= start) & (valid <= end)).sum())
        if result["overlap_rows"] == 0:
            result["status"] = "outside_ohlcv_window"
    return result


def audit(data_dir: Path, *, ohlcv_file: Path | None = None) -> dict:
    files = sorted(data_dir.glob("*.feather"))
    ohlcv_range = None
    if ohlcv_file and ohlcv_file.exists():
        ohlcv = pd.read_feather(ohlcv_file)
        dates = pd.to_datetime(ohlcv.get("date"), utc=True, errors="coerce").dropna()
        if not dates.empty:
            ohlcv_range = (dates.min(), dates.max())
    reports = [_audit_file(path, ohlcv_range) for path in files]
    by_type = {kind: [r for r in reports if r["kind"] == kind] for kind in (*REQUIRED, "ohlcv")}
    return {
        "data_dir": str(data_dir),
        "ohlcv_reference": str(ohlcv_file) if ohlcv_file else None,
        "ohlcv_range": [x.isoformat() for x in ohlcv_range] if ohlcv_range else None,
        "file_count": len(files),
        "coverage": {kind: len(by_type[kind]) for kind in REQUIRED},
        "overlap": {kind: sum(int(x["overlap_rows"]) for x in by_type[kind]) for kind in REQUIRED},
        "missing_feature_types": [kind for kind in REQUIRED if not by_type[kind]],
        "outside_window_types": [
            kind for kind in REQUIRED if by_type[kind] and not any(x["overlap_rows"] for x in by_type[kind])
        ],
        "files": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--ohlcv-file", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.data_dir, ohlcv_file=args.ohlcv_file), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
