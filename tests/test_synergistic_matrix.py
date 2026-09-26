import json
import zipfile
from pathlib import Path

import pandas as pd

from research.evaluation.synergistic_matrix import (
    MatrixCandidate,
    OverlayPolicy,
    _entry_context,
    data_gated_rows,
    simulate_shared_wallet,
)


def _export(path: Path, rows: list[dict]) -> None:
    payload = {"strategy": {"Test": {"strategy_name": "Test", "trades": rows}}}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("backtest-result.json", json.dumps(payload))


def _trade(open_date: str, close_date: str, profit_ratio: float, pair: str = "BTC/USDT") -> dict:
    return {"open_date": open_date, "close_date": close_date, "profit_ratio": profit_ratio, "pair": pair}


def test_entry_context_uses_only_prior_candles() -> None:
    dates = pd.date_range("2025-01-01", periods=8, freq="h", tz="UTC")
    frame = pd.DataFrame({"date": dates, "close": [100, 101, 102, 103, 104, 105, 106, 107], "volume": [1000] * 8})
    policy = OverlayPolicy(min_quote_volume=1, min_volume_ratio=0.5, target_annual_vol=0.25, volatility_lookback=4)
    context = _entry_context(frame, pd.Timestamp("2025-01-01 07:00", tz="UTC"), policy, "1h")
    assert context["available"] is True
    # The candle at 07:00 is not included in the gate calculation.
    assert context["quote_volume"] == 104.5 * 1000


def test_shared_wallet_cash_reserve_reduces_exposure_without_lookahead(tmp_path: Path) -> None:
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    rows = [_trade("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z", 0.10)]
    _export(first, rows)
    _export(second, [_trade("2025-01-01T01:00:00Z", "2025-01-03T00:00:00Z", 0.10, "ETH/USDT")])
    candidates = [MatrixCandidate("a", first, timeframe="1h"), MatrixCandidate("b", second, timeframe="1h")]
    baseline = simulate_shared_wallet(candidates, {"a": 0.5, "b": 0.5}, extra_round_trip_cost=0.0)
    reserve = simulate_shared_wallet(
        candidates,
        {"a": 0.5, "b": 0.5},
        policy=OverlayPolicy(cash_reserve=0.20),
        extra_round_trip_cost=0.0,
    )
    assert baseline["eligible"] is True
    assert reserve["eligible"] is True
    assert reserve["profit_pct"] < baseline["profit_pct"]
    assert reserve["cash_reserve"] == 0.20


def test_missing_market_context_fails_closed_for_liquidity_overlay(tmp_path: Path) -> None:
    export = tmp_path / "lane.zip"
    _export(export, [_trade("2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z", 0.10)])
    result = simulate_shared_wallet(
        [MatrixCandidate("lane", export, timeframe="1h")],
        {"lane": 1.0},
        data_root=tmp_path / "missing-data",
        policy=OverlayPolicy(min_quote_volume=100_000),
        extra_round_trip_cost=0.0,
    )
    assert result["eligible"] is True
    assert result["accepted"] == 0
    assert result["rejections"]["missing_candles"] == 1


def test_data_gated_rows_do_not_promote_missing_event_sources(tmp_path: Path) -> None:
    rows = data_gated_rows(tmp_path)
    assert rows[0]["sleeve"] == "same_venue_cash_and_carry"
    assert rows[0]["status"] == "blocked"
    assert rows[1]["status"] == "blocked"
    assert rows[2]["status"] == "blocked"
