"""Strategy-local generalized-Hurst helper for Freqtrade discovery."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_generalized_hurst(
    series: pd.Series,
    window: int = 96,
    q: float = 1.0,
    lags: tuple[int, ...] = (1, 2, 4, 8, 16),
) -> pd.Series:
    if window < 2 or q <= 0 or not lags or any(lag < 1 for lag in lags):
        raise ValueError("invalid generalized-Hurst parameters")
    values = pd.to_numeric(series, errors="coerce")
    lag_array = np.asarray(lags, dtype=float)
    x = np.log(lag_array)
    x_centered = x - x.mean()
    denominator = float(np.square(x_centered).sum())
    if denominator == 0:
        raise ValueError("lags must contain at least two distinct values")
    moments = [
        values.diff(int(lag)).abs().pow(q).rolling(window, min_periods=window).mean()
        for lag in lags
    ]
    log_moments = np.log(pd.concat(moments, axis=1).replace(0, np.nan))
    y_mean = log_moments.mean(axis=1)
    slope = (
        log_moments.sub(y_mean, axis=0)
        .mul(x_centered, axis=1)
        .sum(axis=1)
        / denominator
        / q
    )
    return slope.where(log_moments.notna().all(axis=1)).replace([np.inf, -np.inf], np.nan)
