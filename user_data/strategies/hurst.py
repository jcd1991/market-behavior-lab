"""Strategy-facing rolling Hurst-style feature helper."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_hurst(close: pd.Series, window: int = 128) -> pd.Series:
    price = pd.to_numeric(close, errors="coerce")
    lags = np.array([1, 2, 4, 8, 16], dtype=float)
    x = np.log(lags)
    centered = x - x.mean()
    denominator = float(np.square(centered).sum())
    matrix = pd.concat(
        [np.log(price.diff(int(lag)).rolling(window, min_periods=window).std(ddof=0).replace(0, np.nan)) for lag in lags],
        axis=1,
    )
    matrix.columns = range(len(lags))
    y_mean = matrix.mean(axis=1)
    slope = matrix.sub(y_mean, axis=0).mul(centered, axis=1).sum(axis=1) / denominator
    return slope.where(matrix.notna().all(axis=1)).replace([np.inf, -np.inf], np.nan)
