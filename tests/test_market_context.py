import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "user_data" / "strategies"))

import pytest

from market_context import derivative_candle_types, parse_pair, reference_pair


def test_pair_context_preserves_spot_and_perpetual_shapes():
    assert parse_pair("btc/usdt").canonical == "BTC/USDT"
    assert parse_pair("btc/usdt:usdt").canonical == "BTC/USDT:USDT"
    assert parse_pair("BTC/USDT", "futures").canonical == "BTC/USDT:USDT"


def test_spot_does_not_request_derivative_candles():
    spot = {"trading_mode": "spot"}
    futures = {"trading_mode": "futures"}
    assert reference_pair("BTC", spot) == "BTC/USDT"
    assert derivative_candle_types(spot) == ()
    assert reference_pair("BTC", futures) == "BTC/USDT:USDT"
    assert derivative_candle_types(futures) == ("mark", "index", "funding_rate")


def test_spot_pair_rejects_settlement_suffix():
    with pytest.raises(ValueError):
        parse_pair("BTC/USDT:USDT", "spot")
