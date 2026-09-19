"""Audit optional derivative-data coverage before using it as a feature."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def inspect_file(path: Path) -> dict:
    frame = pd.read_feather(path)
    date = pd.to_datetime(frame.get("date"), utc=True, errors="coerce")
    non_null = int(date.notna().sum())
    return {
        "file": str(path),
        "rows": int(len(frame)),
        "date_min": date.min().isoformat() if non_null else None,
        "date_max": date.max().isoformat() if non_null else None,
        "columns": list(frame.columns),
        "status": "usable" if non_null else "empty",
    }


def audit(data_dir: Path) -> dict:
    files = sorted(data_dir.glob("*.feather"))
    by_type: dict[str, list[dict]] = {}
    for path in files:
        name = path.name
        if "funding_rate" in name:
            kind = "funding_rate"
        elif "mark" in name:
            kind = "mark"
        elif "index" in name:
            kind = "index"
        elif "open_interest" in name or "openInterest" in name:
            kind = "open_interest"
        else:
            kind = "ohlcv"
        by_type.setdefault(kind, []).append(inspect_file(path))
    required = ("funding_rate", "mark", "index", "open_interest")
    return {
        "data_dir": str(data_dir),
        "file_count": len(files),
        "coverage": {kind: len(by_type.get(kind, [])) for kind in required},
        "missing_feature_types": [kind for kind in required if not by_type.get(kind)],
        "files": by_type,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.data_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
