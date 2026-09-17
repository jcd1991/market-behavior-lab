import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "user_data" / "strategies"))

from lib.regime_detector import REGIME_COLUMNS, RegimeConfig, populate_regime_indicators  # noqa: E402


def test_detector_adds_expected_columns_without_future_inputs() -> None:
    rows = 420
    close = 100.0 + np.linspace(0.0, 25.0, rows) + np.sin(np.arange(rows) / 7.0)
    frame = pd.DataFrame(
        {
            "open": close - 0.4,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(rows, 1000.0),
        }
    )

    result = populate_regime_indicators(frame.copy(), RegimeConfig())

    assert len(REGIME_COLUMNS) == 33
    assert set(REGIME_COLUMNS).issubset(result.columns)
    assert result.loc[0, "composite_regime"] == "WARMUP"
    assert result["composite_regime"].notna().all()
