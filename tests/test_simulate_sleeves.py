import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "evaluation"))

from simulate_sleeves import Trade, simulate  # noqa: E402


def _trade(sleeve: str, opened: str, closed: str, pnl: float) -> Trade:
    return Trade(sleeve, "BTC/USDT", pd.Timestamp(opened, tz="UTC"), pd.Timestamp(closed, tz="UTC"), pnl)


def test_shared_capacity_rejects_overlapping_entries_and_scales_pnl() -> None:
    trades = [
        _trade("a", "2025-01-01 00:00", "2025-01-01 03:00", 10.0),
        _trade("b", "2025-01-01 01:00", "2025-01-01 04:00", 20.0),
        _trade("c", "2025-01-01 02:00", "2025-01-01 05:00", 30.0),
    ]
    result = simulate(trades, {"a": 50.0, "b": 25.0, "c": 25.0}, max_open_positions=2)
    assert result["trades"] == 2
    assert result["skipped_trades"] == 1
    assert result["profit_abs"] == 10.0
    assert result["max_open_positions_observed"] == 2
