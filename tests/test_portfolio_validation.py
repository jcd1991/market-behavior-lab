import json
import zipfile
from pathlib import Path

from research.evaluation.portfolio_validation import (
    bootstrap_report,
    concentration_report,
    load_detailed_trades,
    replay_order_sensitivity,
)
from research.evaluation.synergistic_matrix import MatrixCandidate


def _export(path: Path, rows: list[dict]) -> None:
    payload = {"strategy": {"Test": {"strategy_name": "Test", "trades": rows}}}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("backtest-result.json", json.dumps(payload))


def _trade(open_date: str, close_date: str, profit_abs: float, pair: str = "BTC/USDT") -> dict:
    return {
        "open_date": open_date,
        "close_date": close_date,
        "profit_ratio": profit_abs / 1000.0,
        "profit_abs": profit_abs,
        "stake_amount": 100.0,
        "pair": pair,
    }


def test_concentration_reports_top_trade_and_pair_dependence(tmp_path: Path) -> None:
    export = tmp_path / "lane.zip"
    _export(
        export,
        [
            _trade("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z", 100.0),
            _trade("2025-02-01T00:00:00Z", "2025-02-02T00:00:00Z", 20.0, "ETH/USDT"),
            _trade("2025-03-01T00:00:00Z", "2025-03-02T00:00:00Z", -10.0, "ETH/USDT"),
        ],
    )
    trades = load_detailed_trades(export)
    report = concentration_report(trades)
    assert report["trade_count"] == 3
    assert report["top_trade_share_of_gains"] == 100.0 / 120.0
    assert report["profit_without_top_trade_pct"] == 1.0
    assert report["top_pair_share_of_gains"] == 100.0 / 120.0


def test_bootstrap_is_seeded_and_reports_positive_probability(tmp_path: Path) -> None:
    export = tmp_path / "lane.zip"
    _export(export, [_trade(f"2025-01-{day:02d}T00:00:00Z", f"2025-01-{day + 1:02d}T00:00:00Z", 10.0) for day in range(1, 5)])
    trades = load_detailed_trades(export)
    first = bootstrap_report(trades, iterations=200, seed=7)
    second = bootstrap_report(trades, iterations=200, seed=7)
    assert first == second
    assert first["trade_bootstrap"]["probability_positive_pct"] == 100.0
    assert first["month_block_bootstrap"]["months"] == 1


def test_order_sensitivity_replays_shared_wallet_priority(tmp_path: Path) -> None:
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    _export(first, [_trade("2025-01-01T00:00:00Z", "2025-01-03T00:00:00Z", 100.0)])
    _export(second, [_trade("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z", 100.0, "ETH/USDT")])
    result = replay_order_sensitivity(
        [MatrixCandidate("first", first), MatrixCandidate("second", second)],
        {"first": 0.5, "second": 0.5},
        extra_round_trip_cost=0.0,
    )
    assert result["permutations"] == 2
    assert result["eligible"] is True
    assert result["all_orders_positive"] is True
