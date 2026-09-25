#!/usr/bin/env python3
"""Normalize public Binance/OKX archives into Freqtrade-compatible candles.

The output is deliberately limited to the OHLCV candle contract consumed by
Freqtrade. Venue, market type, source URL, and the raw input files are kept in
a sidecar manifest because they are provenance, not candle columns. This
utility never combines venues and never turns a reference feed into execution
truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile
from typing import Iterable

import pandas as pd


BINANCE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base_volume",
    "taker_buy_quote_volume", "ignore",
]
OKX_COLUMNS = [
    "instrument_name", "open", "high", "low", "close", "volume",
    "volume_currency", "quote_volume", "open_time", "confirm",
]
OUTPUT_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def _archive_csv(path: Path) -> tuple[str, bytes]:
    if path.suffix.lower() != ".zip":
        raise ValueError(f"expected a ZIP archive: {path}")
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if not name.endswith("/") and name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"expected exactly one CSV in {path}, found {members}")
        return members[0], archive.read(members[0])


def _read_csv_bytes(payload: bytes, *, names: list[str]) -> pd.DataFrame:
    from io import BytesIO

    frame = pd.read_csv(BytesIO(payload), header=None)
    known_headers = {name.lower() for name in names}
    if not frame.empty and str(frame.iloc[0, 0]).strip().lower() in known_headers:
        frame = frame.iloc[1:].reset_index(drop=True)
    if frame.shape[1] < len(names):
        raise ValueError(f"archive row has {frame.shape[1]} columns; expected at least {len(names)}")
    frame = frame.iloc[:, : len(names)].copy()
    frame.columns = names
    return frame


def _timestamp_unit(values: pd.Series) -> str:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        raise ValueError("archive has no numeric timestamps")
    magnitude = float(numeric.abs().median())
    if magnitude >= 1e17:
        return "ns"
    if magnitude >= 1e14:
        return "us"
    if magnitude >= 1e11:
        return "ms"
    return "s"


def _finalize(frame: pd.DataFrame, *, timestamp_col: str) -> pd.DataFrame:
    output = frame[[timestamp_col, "open", "high", "low", "close", "volume"]].copy()
    timestamp = output.pop(timestamp_col)
    output["date"] = pd.to_datetime(
        pd.to_numeric(timestamp, errors="coerce"),
        unit=_timestamp_unit(timestamp),
        utc=True,
        errors="coerce",
    )
    for column in ["open", "high", "low", "close", "volume"]:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    output = output.dropna(subset=OUTPUT_COLUMNS).sort_values("date")
    output = output.drop_duplicates(subset=["date"], keep="last")
    output = output[OUTPUT_COLUMNS].reset_index(drop=True)
    if output.empty:
        raise ValueError("archive produced no valid OHLCV rows")
    return output


def read_binance_archive(path: Path) -> pd.DataFrame:
    _member, payload = _archive_csv(path)
    return _finalize(_read_csv_bytes(payload, names=BINANCE_COLUMNS), timestamp_col="open_time")


def read_okx_archive(path: Path) -> pd.DataFrame:
    _member, payload = _archive_csv(path)
    return _finalize(_read_csv_bytes(payload, names=OKX_COLUMNS), timestamp_col="open_time")


def normalize_archives(paths: Iterable[Path], *, provider: str) -> pd.DataFrame:
    if provider not in {"binance", "okx"}:
        raise ValueError(f"unsupported provider: {provider}")
    reader = read_binance_archive if provider == "binance" else read_okx_archive
    frames = [reader(path) for path in paths]
    if not frames:
        raise ValueError("at least one archive is required")
    output = pd.concat(frames, ignore_index=True).sort_values("date")
    return output.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)


def write_normalized(
    inputs: list[Path],
    output: Path,
    *,
    provider: str,
    pair: str,
    market_type: str,
    source: str,
) -> dict[str, object]:
    if market_type == "spot" and ":" in pair:
        raise ValueError(f"spot pair must not contain a settlement suffix: {pair}")
    if market_type == "futures" and ":" not in pair:
        raise ValueError(f"futures pair must preserve settlement currency: {pair}")
    frame = normalize_archives(inputs, provider=provider)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_feather(output)
    manifest = {
        "schema_version": "normalized-ohlcv.v1",
        "provider": provider,
        "pair": pair,
        "market_type": market_type,
        "source": source,
        "execution_truth": False,
        "inputs": [str(path) for path in inputs],
        "rows": int(len(frame)),
        "start": str(frame.iloc[0]["date"]),
        "end": str(frame.iloc[-1]["date"]),
        "columns": OUTPUT_COLUMNS,
        "timestamps": "UTC",
        "venue_mixing": "forbidden",
    }
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("binance", "okx"), required=True)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pair", required=True)
    parser.add_argument("--market-type", choices=("spot", "futures"), required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    result = write_normalized(
        args.input,
        args.output,
        provider=args.provider,
        pair=args.pair,
        market_type=args.market_type,
        source=args.source,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
