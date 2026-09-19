import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "research" / "evaluation"))

from orderbook_cost_snapshot import measure


def test_orderbook_measurement_reports_spread_and_depth_cost() -> None:
    result = measure(
        {
            "bids": [[99.0, 1.0], [98.0, 1.0]],
            "asks": [[101.0, 1.0], [102.0, 1.0]],
        },
        150.0,
    )
    assert result["spread_bps"] == 200.0
    assert result["buy_slippage_bps"] is not None
    assert result["sell_slippage_bps"] is not None
    assert result["buy_slippage_bps"] > 0
    assert result["sell_slippage_bps"] > 0
