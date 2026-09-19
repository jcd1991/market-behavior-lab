"""Causal rolling Hurst-style features for crypto research."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_hurst(close: pd.Series, window: int = 128) -> pd.Series:
    """Estimate H from rolling log(std(delta price)) across fixed lags.

    This is a lightweight diagnostic, not a claim that one Hurst estimator is
    universally correct. A value above 0.5 is treated as persistence and a
    value below 0.5 as anti-persistence by the experimental strategy.
    """
    price = pd.to_numeric(close, errors="coerce")
    lags = np.array([1, 2, 4, 8, 16], dtype=float)
    x = np.log(lags)
    x_centered = x - x.mean()
    denominator = float(np.square(x_centered).sum())
    log_std = []
    for lag in lags.astype(int):
        diff = price.diff(lag)
        log_std.append(np.log(diff.rolling(window, min_periods=window).std(ddof=0).replace(0, np.nan)))
    matrix = pd.concat(log_std, axis=1)
    matrix.columns = range(len(lags))
    y_mean = matrix.mean(axis=1)
    slope = ((matrix.sub(y_mean, axis=0)).mul(x_centered, axis=1).sum(axis=1) / denominator)
    slope = slope.where(matrix.notna().all(axis=1))
    return slope.replace([np.inf, -np.inf], np.nan)
