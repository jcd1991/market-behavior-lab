#!/usr/bin/env python3
"""Benchmark exact execution candles against a buy-and-hold return."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def benchmark(path: Path, *, start: str | None, end: str | None, fee_bps_per_side: float) -> dict[str, float | str]:
    frame = pd.read_feather(path)
    if "date" not in frame or "close" not in frame:
        raise ValueError(f"missing date/close columns: {path}")
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"]).sort_values("date")
    if start:
        frame = frame.loc[frame["date"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        frame = frame.loc[frame["date"] <= pd.Timestamp(end, tz="UTC")]
    if frame.empty:
        raise ValueError(f"no candles in requested window: {path}")
    first = float(frame.iloc[0]["close"])
    last = float(frame.iloc[-1]["close"])
    gross = last / first - 1.0
    fee = float(fee_bps_per_side) / 10000.0
    net = (1.0 + gross) * (1.0 - fee) ** 2 - 1.0
    running_max = frame["close"].cummax()
    drawdown = frame["close"] / running_max - 1.0
    return {
        "path": str(path),
        "start": str(frame.iloc[0]["date"]),
        "end": str(frame.iloc[-1]["date"]),
        "candles": int(len(frame)),
        "buy_hold_gross_pct": gross * 100.0,
        "buy_hold_net_pct": net * 100.0,
        "buy_hold_max_drawdown_pct": abs(float(drawdown.min())) * 100.0,
        "fee_bps_per_side": float(fee_bps_per_side),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--fee-bps-per-side", type=float, default=5.0)
    parser.add_argument("--input", action="append", required=True, help="label:path-to-feather")
    args = parser.parse_args()
    output = []
    for value in args.input:
        label, path = value.split(":", 1)
        result = benchmark(Path(path), start=args.start, end=args.end, fee_bps_per_side=args.fee_bps_per_side)
        result["label"] = label
        output.append(result)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
