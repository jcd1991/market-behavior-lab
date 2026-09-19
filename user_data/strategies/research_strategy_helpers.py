"""Small causal helpers shared by independent crypto research lanes."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas import DataFrame


def utc_series(values: pd.Series) -> pd.Series:
    # Freqtrade can provide candle dates at ns precision while informative
    # data may arrive at ms precision.  Normalize both to one timezone-aware
    # dtype before merge_asof or cross-sectional alignment.
    return pd.to_datetime(values, utc=True, errors="coerce").astype("datetime64[ns, UTC]")


def scheduled_bars(dataframe: DataFrame, hours: int) -> pd.Series:
    """Return bars on a UTC schedule without using future rows."""
    dates = utc_series(dataframe["date"])
    step = max(1, int(hours))
    return dates.dt.minute.eq(0) & dates.dt.hour.mod(step).eq(0)


def merge_close(left: DataFrame, right: DataFrame, column: str) -> DataFrame:
    """Backward-only close merge for a reference pair."""
    work = left.copy()
    work["__date"] = utc_series(work["date"])
    ref = right[["date", "close"]].copy()
    ref["__date"] = utc_series(ref["date"])
    ref[column] = pd.to_numeric(ref["close"], errors="coerce")
    ref = ref[["__date", column]].dropna(subset=["__date"]).sort_values("__date")
    work = work.sort_values("__date")
    merged = pd.merge_asof(work, ref, on="__date", direction="backward")
    return merged.sort_index()


def empty_signal_columns(dataframe: DataFrame, prefix: str) -> DataFrame:
    dataframe[f"{prefix}_signal_long"] = False
    dataframe[f"{prefix}_signal_short"] = False
    return dataframe


def finite(value: object) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False
