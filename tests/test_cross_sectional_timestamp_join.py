from __future__ import annotations

import pandas as pd

from user_data.strategies.CrossSectionalRotation import CrossSectionalRotation


def test_cross_sectional_derivative_join_normalizes_datetime_resolution() -> None:
    base = pd.DataFrame({"__date": pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z"]).astype("datetime64[ms, UTC]")})
    source = pd.DataFrame({"__date": pd.to_datetime(["2024-01-01T00:30:00Z"]).astype("datetime64[ns, UTC]"), "value": [3.5]})
    result = CrossSectionalRotation._merge_asof_numeric_series(base, source, "value")
    assert pd.isna(result.iloc[0])
    assert result.iloc[1] == 3.5
