"""Causal generalized-Hurst features for residual research."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_generalized_hurst(
    series: pd.Series,
    window: int = 96,
    q: float = 1.0,
    lags: tuple[int, ...] = (1, 2, 4, 8, 16),
) -> pd.Series:
    """Estimate generalized H from rolling absolute increment moments.

    For each lag ``l`` this estimates E[|X[t]-X[t-l]|**q] and regresses its
    log against log(l).  Since the moments are rolling and never centered on
    future observations, the result is safe to use as an entry filter.  This
    is an exploratory estimator, not a claim of a universal Hurst definition.
    """
    if window < 2:
        raise ValueError("window must be at least 2")
    if q <= 0:
        raise ValueError("q must be positive")
    if not lags or any(lag < 1 for lag in lags):
        raise ValueError("lags must contain positive integers")

    values = pd.to_numeric(series, errors="coerce")
    lag_array = np.asarray(lags, dtype=float)
    x = np.log(lag_array)
    x_centered = x - x.mean()
    denominator = float(np.square(x_centered).sum())
    if denominator == 0:
        raise ValueError("lags must contain at least two distinct values")

    moments = []
    for lag in lags:
        increment = values.diff(int(lag)).abs().pow(q)
        moments.append(increment.rolling(window, min_periods=window).mean())
    matrix = pd.concat(moments, axis=1).replace(0, np.nan)
    log_moments = np.log(matrix)
    y_mean = log_moments.mean(axis=1)
    slope = (
        log_moments.sub(y_mean, axis=0)
        .mul(x_centered, axis=1)
        .sum(axis=1)
        / denominator
        / q
    )
    return slope.where(log_moments.notna().all(axis=1)).replace([np.inf, -np.inf], np.nan)


def anti_persistent_residual(
    residual: pd.Series,
    window: int = 96,
    max_hurst: float = 0.48,
    q: float = 1.0,
) -> pd.Series:
    """Return a boolean selector for residuals below the Hurst threshold."""
    return (rolling_generalized_hurst(residual, window=window, q=q) <= max_hurst).fillna(False)
