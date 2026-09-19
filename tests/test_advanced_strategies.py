import numpy as np
import pandas as pd

from research.evaluation.advanced_strategies import (
    correlation_clusters,
    factor_ensemble,
    kalman_hedge_ratio,
    realized_volatility,
    signed_jump_score,
    volatility_target_scale,
)


def test_volatility_tools_are_causal_and_bounded():
    close = pd.Series(np.linspace(100, 120, 160) + np.sin(np.arange(160)))
    scale = volatility_target_scale(close, window=24)
    jump = signed_jump_score(close, window=24)
    assert realized_volatility(close, 24).iloc[:24].isna().all()
    assert scale.between(0.25, 1.50).all()
    changed = close.copy()
    changed.iloc[-1] = 10_000
    assert scale.iloc[-2] == volatility_target_scale(changed, 24).iloc[-2]
    assert jump.iloc[:24].isna().all()


def test_factor_ensemble_and_clusters_have_expected_shape():
    frame = pd.DataFrame({"close": np.linspace(100, 140, 220), "volume": np.ones(220)})
    score = factor_ensemble(frame, (12, 36, 84))
    assert len(score) == len(frame)
    labels = correlation_clusters(pd.DataFrame({"a": np.arange(100), "b": np.arange(100) * 2, "c": np.sin(np.arange(100))}), 0.9)
    assert labels["a"] == labels["b"]
    assert labels["a"] != labels["c"]


def test_kalman_hedge_ratio_is_causal():
    x = pd.Series(np.linspace(10, 20, 100))
    y = 2.0 * x + np.sin(np.arange(100))
    beta = kalman_hedge_ratio(y, x)
    changed = y.copy()
    changed.iloc[-1] += 500
    assert np.isfinite(beta.iloc[-1])
    assert beta.iloc[-2] == kalman_hedge_ratio(changed, x).iloc[-2]
