import pandas as pd

from research.evaluation.cointegration_pairs import pair_diagnostic
from user_data.strategies.CointegrationResidual import CointegrationResidual
from user_data.strategies.SimpleMeanReversionControl import SimpleMeanReversionControl


def test_cointegration_contract_is_venue_neutral_and_utc():
    dates = pd.date_range("2025-01-01", periods=320, freq="h", tz="UTC")
    base = pd.Series(100 + pd.RangeIndex(len(dates)).to_numpy(), index=dates, dtype=float)
    a = pd.DataFrame({"date": dates, "close": base.to_numpy()})
    b = pd.DataFrame({"date": dates, "close": (base * 1.02).to_numpy()})
    result = pair_diagnostic(a.set_index("date"), b.set_index("date"), 240)
    assert result["observations"] == 320
    assert "eligible" in result


def test_strategy_classes_have_explicit_1h_contract():
    assert CointegrationResidual.timeframe == "1h"
    assert CointegrationResidual.can_short is False
    assert SimpleMeanReversionControl.timeframe == "1h"
    assert SimpleMeanReversionControl.can_short is False
