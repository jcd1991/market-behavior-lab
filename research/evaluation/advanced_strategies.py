"""Causal building blocks for the next crypto strategy experiments.

These are deliberately small, dependency-light estimators. They are research
features, not claims that any individual feature predicts returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def realized_volatility(close: pd.Series, window: int = 24) -> pd.Series:
    returns = pd.to_numeric(close, errors="coerce").pct_change()
    return returns.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(window)


def volatility_target_scale(
    close: pd.Series,
    window: int = 24,
    target: float = 0.25,
    floor: float = 0.25,
    ceiling: float = 1.50,
) -> pd.Series:
    if target <= 0 or floor <= 0 or ceiling < floor:
        raise ValueError("invalid volatility target bounds")
    vol = realized_volatility(close, window)
    scale = target / vol.replace(0, np.nan)
    return scale.clip(lower=floor, upper=ceiling).fillna(floor)


def signed_jump_score(close: pd.Series, window: int = 48) -> pd.Series:
    returns = pd.to_numeric(close, errors="coerce").pct_change()
    vol = returns.rolling(window, min_periods=window).std(ddof=0).replace(0, np.nan)
    return (returns / vol).replace([np.inf, -np.inf], np.nan)


def factor_ensemble(frame: pd.DataFrame, lookbacks: tuple[int, ...] = (24, 72, 168)) -> pd.Series:
    close = pd.to_numeric(frame["close"], errors="coerce")
    volume = pd.to_numeric(frame.get("volume"), errors="coerce")
    momentum = pd.concat([close.pct_change(lb) for lb in lookbacks], axis=1).mean(axis=1)
    reversal = -close.pct_change(min(lookbacks))
    liquidity = np.log1p(volume).rolling(min(lookbacks), min_periods=min(lookbacks)).mean()
    volatility = -realized_volatility(close, min(lookbacks))
    factors = pd.concat([momentum, reversal, liquidity, volatility], axis=1)
    ranks = factors.rank(pct=True, axis=0)
    return ((ranks - 0.5) * 2.0).mean(axis=1)


def correlation_clusters(returns: pd.DataFrame, threshold: float = 0.70) -> dict[str, int]:
    """Return deterministic connected-component correlation clusters."""
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    corr = returns.corr().fillna(0.0).abs()
    labels: dict[str, int] = {}
    cluster = 0
    for name in corr.columns:
        if name in labels:
            continue
        stack = [name]
        labels[name] = cluster
        while stack:
            current = stack.pop()
            neighbors = corr.index[corr.loc[current] >= threshold].tolist()
            for neighbor in neighbors:
                if neighbor not in labels:
                    labels[neighbor] = cluster
                    stack.append(neighbor)
        cluster += 1
    return labels


def kalman_hedge_ratio(y: pd.Series, x: pd.Series, delta: float = 1e-4, noise: float = 1e-3) -> pd.Series:
    """Causal one-state Kalman estimate for y ~= beta * x."""
    if delta <= 0 or noise <= 0:
        raise ValueError("delta and noise must be positive")
    yv = pd.to_numeric(y, errors="coerce")
    xv = pd.to_numeric(x, errors="coerce")
    beta = 0.0
    covariance = 1.0
    values: list[float] = []
    for observed_y, observed_x in zip(yv, xv):
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
    return pd.Series(values, index=y.index, dtype=float)


def kalman_residual(y: pd.Series, x: pd.Series, delta: float = 1e-4, noise: float = 1e-3) -> pd.Series:
    beta = kalman_hedge_ratio(y, x, delta=delta, noise=noise)
    return pd.to_numeric(y, errors="coerce") - beta * pd.to_numeric(x, errors="coerce")
