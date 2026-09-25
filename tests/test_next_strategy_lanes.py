import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "user_data" / "strategies"))

from research.evaluation.cash_carry import evaluate_pair
from research.evaluation.cointegration_book import simulate_pair
from research_strategy_helpers import execution_cost_floor, quote_volume_features
from user_data.strategies.MarketNeutralCointegrationBook import MarketNeutralCointegrationBook
from user_data.strategies.RiskManagedCrossSectionalTrend import RiskManagedCrossSectionalTrend
from user_data.strategies.RiskManagedCrossSectionalTrend import RiskManagedCrossSectionalTrendSpot
from user_data.strategies.VolatilityManagedTrendCash import VolatilityManagedTrendCash, VolatilityManagedTrendCashSpot


def _write_frame(path: Path, dates, close, **extra):
    frame = pd.DataFrame({"date": dates, "close": close, **extra})
    frame.to_feather(path)


def test_new_strategy_contracts_are_explicit():
    assert MarketNeutralCointegrationBook.can_short is True
    assert RiskManagedCrossSectionalTrend.timeframe == "1h"
    assert RiskManagedCrossSectionalTrendSpot.can_short is False
    assert VolatilityManagedTrendCash.stoploss < 0
    assert VolatilityManagedTrendCashSpot.can_short is False


def test_execution_cost_and_liquidity_filters_are_causal():
    assert execution_cost_floor({"fee": 0.001, "research_spread_bps": 10, "research_slippage_bps": 10, "research_safety_bps": 10}) == 0.005
    frame = pd.DataFrame({"close": [100.0] * 8, "volume": [1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 2.0]})
    result = quote_volume_features(frame, "test", window=4)
    assert result["test_quote_volume"].iloc[-1] == 200.0
    assert pd.isna(result["test_volume_ratio"].iloc[0])
    assert result["test_volume_ratio"].iloc[-1] >= 1.0


def test_cash_carry_rejects_cross_venue_inputs(tmp_path: Path):
    result = evaluate_pair(*(tmp_path / name for name in ("spot.feather", "perp.feather", "funding.feather", "index.feather")), "binanceus", "okx")
    assert result["eligible"] is False
    assert result["reason"] == "venue_mismatch"


def test_cash_carry_reports_missing_same_venue_inputs(tmp_path: Path):
    result = evaluate_pair(*(tmp_path / name for name in ("spot.feather", "perp.feather", "funding.feather", "index.feather")), "okx", "okx")
    assert result["eligible"] is False
    assert result["reason"] == "missing_input"
    assert result["missing"] == ["funding", "index", "perp", "spot"]


def test_cash_carry_contract_uses_utc_and_costs(tmp_path: Path):
    dates = pd.date_range("2025-01-01", periods=5, freq="h", tz="UTC")
    _write_frame(tmp_path / "spot.feather", dates, [100, 100, 100, 100, 100])
    _write_frame(tmp_path / "perp.feather", dates, [101, 101, 100.5, 100.5, 100])
    _write_frame(tmp_path / "index.feather", dates, [100, 100, 100, 100, 100])
    _write_frame(tmp_path / "funding.feather", dates, [0.001] * 5, funding_rate=[0.001] * 5)
    result = evaluate_pair(*(tmp_path / name for name in ("spot.feather", "perp.feather", "funding.feather", "index.feather")), "okx", "okx", round_trip_cost=0.002)
    assert result["eligible"] is True
    assert result["observations"] == 5
    assert result["round_trip_cost"] == 0.002


def test_cointegration_book_opens_two_leg_causal_positions():
    dates = pd.date_range("2025-01-01", periods=80, freq="h", tz="UTC")
    reference = 100.0 + pd.Series(range(80), dtype=float).to_numpy()
    asset = reference * np.exp(0.02 * np.sin(pd.Series(range(80), dtype=float).to_numpy() / 3.0))
    result = simulate_pair(
        pd.DataFrame({"date": dates, "close": asset}).set_index("date"),
        pd.DataFrame({"date": dates, "close": reference}).set_index("date"),
        venue="okx",
        window=20,
        entry_z=0.8,
        exit_z=0.1,
        min_corr=0.2,
        max_half_life=120,
        round_trip_cost=0.0,
    )
    assert result["eligible"] is True
    assert result["entries"] > 0
    assert result["closed_or_force_closed"] >= result["entries"]
