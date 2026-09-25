from __future__ import annotations

import pandas as pd

from research.evaluation.cash_carry import CarryAssumptions, evaluate_pair
from research.evaluation.cross_sectional_portfolio import PortfolioPolicy, build_features, simulate_portfolio
from research.evaluation.execution_foundation import WalletPolicy, reconcile_fills, simulate_shared_wallet
from research.evaluation.microstructure import (
    FeeTier,
    VenueCostModel,
    depth_cost_bps,
    cost_curve,
    normalize_minute_trades,
    normalize_orderbook_snapshots,
    point_in_time_universe,
)
from research.evaluation.orderflow_market_making import simulate_passive_quotes


def test_microstructure_normalizes_utc_trades_and_l2_depth() -> None:
    trades = normalize_minute_trades(
        pd.DataFrame({"date": ["2025-01-01 00:00"], "price": [100], "quantity": [2], "side": ["buy"]}),
        venue="Demo", pair="btc/usdt:usdt", source="fixture", market_type="futures",
    )
    books = normalize_orderbook_snapshots(
        pd.DataFrame({"timestamp": ["2025-01-01T00:00:00Z"], "bids": [[[99, 1], [98, 2]]], "asks": [[[101, 1], [102, 2]]]}),
        venue="Demo", pair="BTC/USDT:USDT", source="fixture", market_type="futures",
    )
    assert str(trades.loc[0, "timestamp"].tz) == "UTC"
    assert trades.loc[0, "pair"] == "BTC/USDT:USDT"
    assert books.loc[0, "spread_bps"] == 200.0
    assert depth_cost_bps(books.loc[0].to_dict(), side="buy", notional=150)["filled"] is True
    curve = cost_curve(books, [50, 150], costs=VenueCostModel("demo", (FeeTier("retail", 10, 20),), "retail"))
    assert len(curve) == 2
    assert curve["filled"].tolist() == [True, True]


def test_point_in_time_universe_excludes_future_listing() -> None:
    candles = pd.DataFrame({"timestamp": pd.to_datetime(["2025-01-01", "2025-02-01"], utc=True), "pair": ["BTC/USDT", "ETH/USDT"], "close": [1, 2], "volume": [100, 100]})
    membership = pd.DataFrame({"effective_at": pd.to_datetime(["2025-01-15"], utc=True), "pair": ["ETH/USDT"]})
    out = point_in_time_universe(candles, membership)
    assert out["pair"].tolist() == ["ETH/USDT"]
    assert out["timestamp"].iloc[0] == pd.Timestamp("2025-02-01", tz="UTC")


def test_shared_wallet_and_fill_reconciliation_are_explicit() -> None:
    trades = pd.DataFrame({
        "open_time": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 01:00"], utc=True),
        "close_time": pd.to_datetime(["2025-01-01 03:00", "2025-01-01 04:00"], utc=True),
        "pair": ["BTC/USDT", "BTC/USDT"], "side": ["long", "long"], "profit_ratio": [0.05, 0.05],
    })
    costs = VenueCostModel("demo", (FeeTier("retail", 10, 20),), "retail", safety_bps=5)
    result = simulate_shared_wallet(trades, policy=WalletPolicy(max_open_positions=1, max_pair_fraction=0.5), costs=costs)
    assert result["accepted"] == 1
    assert result["rejections"] == {"pair_overlap": 1}
    expected = pd.DataFrame({"order_id": ["a"], "price": [100.0], "amount": [1.0], "timestamp": ["2025-01-01T00:00Z"]})
    actual = expected.assign(price=[100.1])
    report = reconcile_fills(expected, actual, price_tolerance_bps=20)
    assert report["within_tolerance"] == 1


def test_cross_sectional_portfolio_requires_point_in_time_membership() -> None:
    dates = pd.date_range("2025-01-01", periods=90, freq="h", tz="UTC")
    rows = []
    for pair, drift in (("BTC/USDT", 0.001), ("ETH/USDT", 0.0005), ("SOL/USDT", -0.0002)):
        for index, date in enumerate(dates):
            rows.append({"timestamp": date, "pair": pair, "close": 100 * (1 + drift) ** index, "volume": 1000})
    candles = pd.DataFrame(rows)
    membership = pd.DataFrame({"effective_at": [dates[0], dates[0], dates[0]], "pair": ["BTC/USDT", "ETH/USDT", "SOL/USDT"]})
    features = build_features(candles, membership, policy=PortfolioPolicy(lookback=12, volatility_window=12))
    result = simulate_portfolio(features, policy=PortfolioPolicy(lookback=12, volatility_window=12, longs=1, rebalance_every=6))
    assert result["eligible"] is True
    assert result["observations"] == 90


def test_orderflow_lane_fails_closed_without_event_data() -> None:
    result = simulate_passive_quotes(pd.DataFrame(), pd.DataFrame())
    assert result["eligible"] is False
    assert "minute_trades" in result["validation"]["missing"]


def test_carry_still_rejects_cross_venue_before_reading_files(tmp_path) -> None:
    result = evaluate_pair(tmp_path / "spot", tmp_path / "perp", tmp_path / "funding", tmp_path / "index", "binanceus", "okx", assumptions=CarryAssumptions())
    assert result["eligible"] is False
    assert result["reason"] == "venue_mismatch"


def test_carry_accounts_for_two_leg_costs_and_margin_buffer(tmp_path) -> None:
    dates = pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC")
    base = pd.DataFrame({"date": dates, "close": [100.0] * 4})
    spot = tmp_path / "spot.feather"
    perp = tmp_path / "perp.feather"
    funding = tmp_path / "funding.feather"
    index = tmp_path / "index.feather"
    base.to_feather(spot)
    pd.DataFrame({"date": dates, "close": [101.0, 100.05, 100.02, 100.01], "margin_buffer": [0.50] * 4}).to_feather(perp)
    pd.DataFrame({"date": dates, "close": [100.0] * 4}).to_feather(index)
    pd.DataFrame({"date": dates, "funding_rate": [0.0002] * 4}).to_feather(funding)
    result = evaluate_pair(spot, perp, funding, index, "demo", "demo", round_trip_cost=0.001, assumptions=CarryAssumptions(round_trip_cost=0.001, adverse_basis_shock=0.0, venue_failure_cost=0.0))
    assert result["eligible"] is True
    assert result["entries"] == 1
    assert result["data_coverage"]["margin_buffer"] is True
    assert result["profit_ratio"] > 0
