import numpy as np
import pandas as pd

from research.evaluation.hurst import rolling_hurst


def test_rolling_hurst_is_warmup_safe_and_distinguishes_simple_paths():
    rows = 180
    trend = pd.Series(np.linspace(100, 160, rows) + np.sin(np.arange(rows) / 3.0))
    result = rolling_hurst(trend, window=64)
    assert result.iloc[:64].isna().all()
    assert np.isfinite(result.iloc[-1])


def test_rolling_hurst_does_not_use_future_rows():
    base = pd.Series(np.linspace(100, 140, 160))
    changed = base.copy()
    changed.iloc[-1] = 1000
    first = rolling_hurst(base, window=64).iloc[-2]
    second = rolling_hurst(changed, window=64).iloc[-2]
    assert first == second
