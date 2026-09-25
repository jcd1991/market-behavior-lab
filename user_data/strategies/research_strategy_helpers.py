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


def execution_cost_floor(
    config: dict | None,
    *,
    default_fee_rate: float = 0.001,
    default_spread_bps: float = 10.0,
    default_slippage_bps: float = 10.0,
    default_safety_bps: float = 10.0,
) -> float:
    """Return a causal minimum expected move for a round-trip trade.

    These are research assumptions, not exchange quotes.  They can be
    overridden in a local config with ``research_fee_rate``,
    ``research_spread_bps``, ``research_slippage_bps``, and
    ``research_safety_bps``.  None of the fields are optimized by Hyperopt.
    """
    settings = config or {}

    def number(name: str, fallback: float) -> float:
        try:
            return max(0.0, float(settings.get(name, fallback)))
        except (TypeError, ValueError):
            return fallback

    fee_rate = number("research_fee_rate", settings.get("fee", default_fee_rate))
    spread_bps = number("research_spread_bps", default_spread_bps)
    slippage_bps = number("research_slippage_bps", default_slippage_bps)
    safety_bps = number("research_safety_bps", default_safety_bps)
    return 2.0 * fee_rate + (spread_bps + slippage_bps + safety_bps) / 10000.0


def quote_volume_features(dataframe: DataFrame, prefix: str, window: int = 48) -> DataFrame:
    """Add quote-volume and rolling-liquidity-ratio columns without lookahead."""
    close = pd.to_numeric(dataframe["close"], errors="coerce")
    volume = pd.to_numeric(dataframe["volume"], errors="coerce")
    quote_volume = close.abs() * volume.clip(lower=0.0)
    minimum = max(4, int(window) // 2)
    median = quote_volume.replace(0.0, np.nan).rolling(int(window), min_periods=minimum).median()
    dataframe[f"{prefix}_quote_volume"] = quote_volume
    dataframe[f"{prefix}_volume_ratio"] = quote_volume / median.replace(0.0, np.nan)
    return dataframe
