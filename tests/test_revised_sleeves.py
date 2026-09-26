import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "user_data" / "strategies"))

from research.evaluation.revised_sleeves import (  # noqa: E402
    ExecutionCost,
    ResidualPolicy,
    apply_execution_gate,
    evaluate_carry_contract,
    evaluate_delta_hedged_straddle,
    lead_lag_screen,
    simulate_two_leg_residual,
)
from user_data.strategies.BreakoutCrashStateSpot import BreakoutCrashStateSpot  # noqa: E402
from user_data.strategies.LiquidMomentumWeeklySpot import LiquidMomentumWeeklySpot  # noqa: E402
from scripts.fetch_deribit_option_chain import normalize_ticker  # noqa: E402


def _dates(periods: int = 320) -> pd.DatetimeIndex:
    return pd.date_range("2025-01-01", periods=periods, freq="h", tz="UTC")


def _price_frame(values, column="close"):
    dates = _dates(len(values))
    return pd.DataFrame({"date": dates, column: values})


def test_revised_strategy_contracts_are_spot_only_and_slow():
    assert BreakoutCrashStateSpot.can_short is False
    assert LiquidMomentumWeeklySpot.can_short is False
    assert LiquidMomentumWeeklySpot.buy_lms_rebalance_bars.value == 42


def test_same_venue_carry_rejects_missing_index_and_accepts_complete_fixture():
    dates = _dates(12)
    spot = pd.DataFrame({"date": dates, "close": [100.0] * 12})
    perp = pd.DataFrame({"date": dates, "close": [101.0, 101.0, 100.2, 100.1] + [100.0] * 8})
    funding = pd.DataFrame({"date": dates[[0, 2, 4, 6, 8, 10]], "funding_rate": [0.001] * 6})
    index = pd.DataFrame({"date": dates, "close": [100.0] * 12})
    missing = evaluate_carry_contract(spot, perp, funding, None, venue="okx")
    assert missing["eligible"] is False
    assert "index" in missing["missing"]
    complete = evaluate_carry_contract(spot, perp, funding, index, venue="okx", min_basis=0.005, exit_basis=0.003)
    assert complete["eligible"] is True
    assert complete["entries"] >= 1


def test_two_leg_residual_tracks_both_legs_and_is_causal():
    dates = _dates(420)
    reference = 100.0 + np.arange(len(dates)) * 0.01
    asset = reference * np.exp(0.02 * np.sin(np.arange(len(dates)) / 6.0))
    result = simulate_two_leg_residual(
        pd.DataFrame({"date": dates, "close": asset}),
        pd.DataFrame({"date": dates, "close": reference}),
        venue="okx",
        policy=ResidualPolicy(window=48, entry_z=0.8, exit_z=0.1, min_corr=0.2, max_half_life=120),
    )
    assert result["eligible"] is True
    assert result["entries"] > 0
    assert set(result["leg_pnl_proxy"]) == {"asset_leg", "reference_leg"}


def test_execution_gate_covers_costs_and_volume():
    frame = pd.DataFrame({"expected_move_bps": [20.0, 50.0, 100.0], "volume_ratio": [1.0, 0.4, 1.0]})
    result = apply_execution_gate(frame, costs=ExecutionCost(fee_bps_per_side=10, spread_bps_round_trip=10, slippage_bps_round_trip=10, safety_bps_round_trip=5), minimum_volume_ratio=0.75)
    assert result["accepted"] == 1
    assert result["all_in_cost_bps"] == 45.0


def test_lead_lag_screen_uses_past_leader_returns():
    dates = _dates(80)
    leader_returns = np.sin(np.arange(80) / 4.0) * 0.01
    leader = np.cumprod(1.0 + leader_returns) * 100.0
    follower_returns = np.roll(leader_returns, 1)
    follower_returns[0] = 0.0
    follower = np.cumprod(1.0 + follower_returns) * 100.0
    result = lead_lag_screen(
        pd.DataFrame({"timestamp": dates, "price": leader}),
        pd.DataFrame({"timestamp": dates, "price": follower}),
        leader_name="venue-a", follower_name="venue-b", interval="1h", max_lag_steps=2,
    )
    assert result["eligible"] is True
    assert result["best_lag"]["lag_steps"] in {1, 2}


def test_options_lane_fails_closed_without_history_and_accepts_schema_fixture():
    missing = evaluate_delta_hedged_straddle(None)
    assert missing["eligible"] is False
    dates = _dates(12)
    rows = []
    for option_type, delta in (("call", 0.5), ("put", -0.5)):
        for index, date in enumerate(dates):
            rows.append({
                "timestamp": date, "instrument": f"BTC-{option_type}", "option_type": option_type,
                "strike": 100.0, "expiry": dates[-1], "bid": 10.0 - index * 0.1,
                "ask": 10.2 - index * 0.1, "mark_iv": 0.80, "delta": delta,
                "underlying_price": 100.0 + index * 0.1,
            })
    result = evaluate_delta_hedged_straddle(pd.DataFrame(rows), entry_iv=0.70, holding_periods=2)
    assert result["eligible"] is True
    assert result["simulated_trades"] > 0


def test_deribit_snapshot_normalizes_expiry_and_provenance_fields():
    row = normalize_ticker(
        {"instrument_name": "BTC-25SEP26-80000-C", "base_currency": "BTC", "option_type": "call", "strike": 80000, "expiration_timestamp": 1790294400000},
        {"best_bid_price": 0.01, "best_ask_price": 0.02, "mark_price": 0.015, "mark_iv": 0.7, "greeks": {"delta": 0.5}, "underlying_price": 84000},
        "2026-09-25T00:00:00+00:00",
    )
    assert row["expiry"].endswith("+00:00")
    assert row["instrument"] == "BTC-25SEP26-80000-C"
