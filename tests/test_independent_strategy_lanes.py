import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "user_data" / "strategies"))

from CryptoMomentumRotation import CryptoMomentumRotation
from FundingBasisCarry import FundingBasisCarry
from RelativeValueStatArb import RelativeValueStatArb
from ScheduledPortfolioRotation import ScheduledPortfolioRotation
from StandaloneBreakoutTrend import StandaloneBreakoutTrend
from VolatilityCrashGuard import VolatilityCrashGuard
from research_strategy_helpers import scheduled_bars


def test_scheduled_bars_are_utc_and_causal() -> None:
    frame = pd.DataFrame(
        {"date": pd.date_range("2025-01-01", periods=8, freq="1h", tz="UTC")}
    )
    result = scheduled_bars(frame, 4)
    assert result.tolist() == [True, False, False, False, True, False, False, False]


def test_new_lanes_are_independent_and_carry_can_fail_closed() -> None:
    config = {"timeframe": "1h", "exchange": {"pair_whitelist": ["BTC/USDT:USDT"]}}
    assert CryptoMomentumRotation(config).can_short is True
    assert ScheduledPortfolioRotation(config).can_short is False
    assert StandaloneBreakoutTrend(config).can_short is True
    assert RelativeValueStatArb(config).can_short is True
    assert FundingBasisCarry(config).can_short is True
    assert VolatilityCrashGuard(config).can_short is False

    strategy = FundingBasisCarry(config)
    strategy.dp = type("MissingDataProvider", (), {"get_pair_dataframe": lambda *_args, **_kwargs: None})()
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=4, freq="1h", tz="UTC"),
            "open": [100.0] * 4,
            "high": [101.0] * 4,
            "low": [99.0] * 4,
            "close": [100.0] * 4,
            "volume": [1.0] * 4,
        }
    )
    result = strategy.populate_indicators(frame, {"pair": "BTC/USDT:USDT"})
    assert result["enter_long"].sum() == 0
    assert result["enter_short"].sum() == 0
