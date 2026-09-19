"""Freqtrade-local copies of the lightweight advanced research helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def volatility_target_scale(close, window=24, target=0.25, floor=0.25, ceiling=1.50):
    vol = pd.to_numeric(close, errors="coerce").pct_change().rolling(window, min_periods=window).std(ddof=0) * np.sqrt(window)
    return (target / vol.replace(0, np.nan)).clip(lower=floor, upper=ceiling).fillna(floor)


def signed_jump_score(close, window=48):
    returns = pd.to_numeric(close, errors="coerce").pct_change()
    vol = returns.rolling(window, min_periods=window).std(ddof=0).replace(0, np.nan)
    return (returns / vol).replace([np.inf, -np.inf], np.nan)


def factor_ensemble(frame, lookbacks=(24, 72, 168)):
    close = pd.to_numeric(frame["close"], errors="coerce")
    volume = pd.to_numeric(frame.get("volume"), errors="coerce")
    lb = min(lookbacks)
    factors = pd.concat([close.pct_change(x) for x in lookbacks] + [-close.pct_change(lb), np.log1p(volume).rolling(lb, min_periods=lb).mean()], axis=1)
    return ((factors.rank(pct=True, axis=0) - 0.5) * 2.0).mean(axis=1)


def kalman_residual(y, x, delta=1e-4, noise=1e-3):
    beta = 0.0
    covariance = 1.0
    values = []
    for observed_y, observed_x in zip(pd.to_numeric(y, errors="coerce"), pd.to_numeric(x, errors="coerce")):
        if not np.isfinite(observed_y) or not np.isfinite(observed_x):
            values.append(np.nan)
            continue
        covariance += delta
        innovation = observed_y - observed_x * beta
        denominator = observed_x * covariance * observed_x + noise
        gain = covariance * observed_x / denominator if denominator else 0.0
        beta += gain * innovation
        covariance = (1.0 - gain * observed_x) * covariance
        values.append(beta)
    return pd.Series(pd.to_numeric(y, errors="coerce").to_numpy() - np.asarray(values) * pd.to_numeric(x, errors="coerce").to_numpy(), index=y.index)
