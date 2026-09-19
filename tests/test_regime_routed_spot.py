from pathlib import Path
import importlib.util
import sys


STRATEGY_PATH = Path(__file__).parents[1] / "user_data" / "strategies" / "RegimeRoutedSpot.py"


def load_strategy():
    sys.path.insert(0, str(STRATEGY_PATH.parent))
    spec = importlib.util.spec_from_file_location("RegimeRoutedSpot", STRATEGY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.RegimeRoutedSpot


def test_regime_routed_spot_is_long_only_and_spot_safe():
    strategy_cls = load_strategy()
    strategy = strategy_cls({"timeframe": "1h", "exchange": {"pair_whitelist": ["BTC/USD"]}})

    class DataProvider:
        def current_whitelist(self):
            return ["BTC/USD", "ETH/USD"]

    strategy.dp = DataProvider()
    assert strategy.can_short is False
    assert strategy.position_adjustment_enable is False
    assert strategy.buy_trbk_use_funding.value is False
    assert strategy.informative_pairs() == [
        ("BTC/USD", "4h"),
        ("ETH/USD", "4h"),
        ("BTC/USD", "1h"),
        ("ETH/USD", "1h"),
    ]
