import numpy as np
import pandas as pd
import pytest

from research.evaluation.frequency_sensitivity import summarize
from research.evaluation.ghe import anti_persistent_residual, rolling_generalized_hurst


def test_ghe_is_warmup_safe_and_causal():
    base = pd.Series(np.sin(np.arange(220) / 5.0) + np.arange(220) / 100.0)
    changed = base.copy()
    changed.iloc[-1] += 1000
    result = rolling_generalized_hurst(base, window=64)
    assert result.iloc[:64].isna().all()
    assert np.isfinite(result.iloc[-1])
    assert result.iloc[-2] == rolling_generalized_hurst(changed, window=64).iloc[-2]


def test_ghe_selector_blocks_incomplete_windows():
    selector = anti_persistent_residual(pd.Series(np.arange(40, dtype=float)), window=32)
    assert not selector.iloc[:32].any()


def test_frequency_summary_tracks_profit_factor_and_drawdown():
    result = summarize(
        [{"profit_abs": 10}, {"profit_abs": -5}, {"profit_abs": 20}],
        starting_balance=1000,
    )
    assert result["trades"] == 3
    assert result["profit_abs"] == 25
    assert result["profit_factor"] == 6
    assert result["max_drawdown"] == pytest.approx(0.0049505, rel=1e-5)
