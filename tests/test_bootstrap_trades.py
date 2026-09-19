import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "evaluation"))

from bootstrap_trades import bootstrap, grouped_bootstrap  # noqa: E402


def test_bootstrap_is_reproducible_and_reports_observed_result() -> None:
    result = bootstrap([10.0, -5.0, 8.0, -4.0], starting_balance=1000.0, iterations=250, seed=1337)
    repeat = bootstrap([10.0, -5.0, 8.0, -4.0], starting_balance=1000.0, iterations=250, seed=1337)

    assert result == repeat
    assert result["n_trades"] == 4
    assert result["observed"]["profit_abs"] == 9.0
    assert result["bootstrap_intervals"]["profit_abs"]["p05"] <= result["bootstrap_intervals"]["profit_abs"]["p95"]
    assert 0.0 <= result["profitable_resamples_pct"] <= 100.0


def test_grouped_bootstrap_keeps_pair_attribution_separate() -> None:
    trades = [
        {"pair": "BTC/USDT", "profit_abs": 2.0},
        {"pair": "BTC/USDT", "profit_abs": -1.0},
        {"pair": "ETH/USDT", "profit_abs": -3.0},
    ]
    result = grouped_bootstrap(trades, group_by="pair", starting_balance=1000.0, iterations=50, seed=3)
    assert set(result) == {"BTC/USDT", "ETH/USDT"}
    assert result["BTC/USDT"]["n_trades"] == 2
    assert result["ETH/USDT"]["observed"]["profit_abs"] == -3.0
