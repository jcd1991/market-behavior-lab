import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "user_data" / "strategies"))

from research.evaluation.recommended_lanes import (  # noqa: E402
    BreakoutPolicy,
    CostModel,
    MarketOverlay,
    _shared_wallet,
    _trade_frame,
    evaluate_breakout,
    evaluate_momentum,
    market_overlay_scale,
)
from user_data.strategies.BreakoutEnsembleSpot import BreakoutEnsembleSpot  # noqa: E402
from user_data.strategies.LiquidMomentumSpot import LiquidMomentumSpot  # noqa: E402


def _candles(pair: str = "BTC/USDT", periods: int = 260) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=periods, freq="4h", tz="UTC")
    close = 100.0 + np.arange(periods, dtype=float) * 0.15 + np.sin(np.arange(periods) / 4.0)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": np.full(periods, 1000.0),
            "pair": pair,
        }
    )


def test_recommended_strategies_have_explicit_spot_contracts():
    assert BreakoutEnsembleSpot.can_short is False
    assert BreakoutEnsembleSpot.timeframe == "4h"
    assert LiquidMomentumSpot.can_short is False
    assert LiquidMomentumSpot.timeframe == "4h"


def test_breakout_uses_only_prior_channel_and_future_change_does_not_rewrite_past():
    frame = _candles(periods=280)
    policy = BreakoutPolicy(horizons=(12, 24, 48, 96), votes=3)
    original = _trade_frame(frame, policy, CostModel())
    changed = frame.copy()
    changed.loc[changed.index[-1], "close"] = 10_000.0
    changed_result = _trade_frame(changed, policy, CostModel())
    assert original.head(max(0, len(original) - 1)).to_dict("records") == changed_result.head(max(0, len(original) - 1)).to_dict("records")


def test_overlay_is_bounded_and_causal():
    frame = _candles(periods=300)
    scale = market_overlay_scale(frame, MarketOverlay(mode="trend_drawdown"))
    assert set(scale.dropna().unique()).issubset({0.0, 0.5, 1.0})
    changed = frame.copy()
    changed.loc[changed.index[-1], "close"] = 1.0
    assert scale.iloc[-2] == market_overlay_scale(changed, MarketOverlay(mode="trend_drawdown")).iloc[-2]


def test_shared_wallet_realizes_profit_on_close_not_entry():
    trades = pd.DataFrame(
        [
            {"pair": "BTC/USDT", "open_time": "2024-01-01T00:00:00Z", "close_time": "2024-01-02T00:00:00Z", "profit_ratio": 0.10},
            {"pair": "ETH/USDT", "open_time": "2024-01-03T00:00:00Z", "close_time": "2024-01-04T00:00:00Z", "profit_ratio": -0.05},
        ]
    )
    result = _shared_wallet(trades, starting_balance=1000.0, max_open=1, pair_cap=1.0)
    assert result["accepted"] == 2
    assert result["final_balance"] > 1000.0


def test_bounded_recommendation_lanes_run_on_synthetic_universe():
    candles = {pair: _candles(pair, 320) for pair in ("BTC/USDT", "ETH/USDT", "SOL/USDT")}
    breakout = evaluate_breakout(candles, start="2024-01-01", end="2024-03-01")
    momentum = evaluate_momentum(candles, start="2024-01-01", end="2024-03-01")
    assert breakout["lane"] == "breakout"
    assert momentum["eligible"] is True
    assert breakout["costs"]["fee_bps_per_side"] == 10.0
