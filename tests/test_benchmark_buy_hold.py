import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "evaluation"))

from benchmark_buy_hold import benchmark  # noqa: E402


def test_benchmark_applies_round_trip_fees_and_drawdown(tmp_path: Path) -> None:
    path = tmp_path / "BTC_USDT-1h.feather"
    pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=3, freq="h", tz="UTC"),
            "close": [100.0, 80.0, 120.0],
        }
    ).to_feather(path)
    result = benchmark(path, start=None, end=None, fee_bps_per_side=50.0)
    assert result["buy_hold_gross_pct"] == pytest.approx(20.0)
    assert result["buy_hold_net_pct"] == pytest.approx(18.802999999999997)
    assert result["buy_hold_max_drawdown_pct"] == pytest.approx(20.0)
