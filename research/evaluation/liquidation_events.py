"""Validate external liquidation-event research inputs.

Freqtrade candles do not contain market-wide liquidation events.  This module
only validates an explicitly sourced event file and makes its provenance
visible; it does not fabricate or infer liquidation events from OHLCV.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd


REQUIRED_COLUMNS = {
    "timestamp",
    "venue",
    "symbol",
    "side",
    "quantity",
    "price",
    "source",
}


def validate_events(events: pd.DataFrame) -> dict:
    missing = sorted(REQUIRED_COLUMNS - set(events.columns))
    timestamps = pd.to_datetime(events.get("timestamp"), utc=True, errors="coerce")
    source_values = sorted({str(x) for x in events.get("source", pd.Series(dtype=str)).dropna().unique()})
    return {
        "rows": int(len(events)),
        "missing_columns": missing,
        "valid": not missing and bool(timestamps.notna().all()),
        "timestamp_min": timestamps.min().isoformat() if timestamps.notna().any() else None,
        "timestamp_max": timestamps.max().isoformat() if timestamps.notna().any() else None,
        "sources": source_values,
        "historical_backtest_ready": False,
        "reason": "requires venue-wide historical event coverage joined to the exact execution venue",
    }
