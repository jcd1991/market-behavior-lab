"""Create a higher-timeframe OHLCV file from lower-timeframe data.

This is for research-only venue adapters where the exchange does not expose
the exact timeframe requested by a strategy. The source and target timeframe
must be recorded in the run metadata; this is not a substitute for native
exchange candles when execution truth matters.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def resample_file(source: Path, target: Path, timeframe: str) -> None:
    frame = pd.read_feather(source)
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").set_index("date")
    output = frame[["open", "high", "low", "close", "volume"]].resample(timeframe).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open", "high", "low", "close"])
    output.reset_index().to_feather(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeframe", default="4h")
    parser.add_argument("--pairs", nargs="+", required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for pair in args.pairs:
        source = args.input_dir / f"{pair.replace('/', '_')}-1h.feather"
        target = args.output_dir / f"{pair.replace('/', '_')}-{args.timeframe}.feather"
        if not source.exists():
            raise FileNotFoundError(source)
        resample_file(source, target, args.timeframe)
        print(f"{source} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
