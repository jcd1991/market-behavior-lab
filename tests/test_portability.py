from __future__ import annotations

import pandas as pd

from research.evaluation.portability import (
    build_static_membership,
    resample_ohlcv,
    synchronized_panel,
)


def _frame(pair: str = "BTC/USDT") -> pd.DataFrame:
    dates = pd.date_range("2024-06-01", periods=8, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "date": dates,
            "open": range(100, 108),
            "high": range(101, 109),
            "low": range(99, 107),
            "close": range(100, 108),
            "volume": [1.0] * 8,
            "pair": [pair] * 8,
        }
    )


def test_resample_preserves_utc_ohlcv_boundaries() -> None:
    result = resample_ohlcv(_frame(), "1h")
    assert list(result["date"]) == list(pd.date_range("2024-06-01", periods=2, freq="1h", tz="UTC"))
    assert result.iloc[0]["open"] == 100
    assert result.iloc[0]["high"] == 104
    assert result.iloc[0]["low"] == 99
    assert result.iloc[0]["close"] == 103
    assert result.iloc[0]["volume"] == 4


def test_resample_discards_partial_final_bar() -> None:
    result = resample_ohlcv(_frame().iloc[:-1].copy(), "1h")
    assert len(result) == 1
    assert result.iloc[-1]["date"] == pd.Timestamp("2024-06-01T00:00:00Z")


def test_synchronized_panel_rejects_missing_timestamps() -> None:
    first = _frame()
    second = _frame("ETH/USDT").iloc[:-1].copy()
    report = synchronized_panel({"BTC/USDT": first, "ETH/USDT": second})
    assert report["synchronized"] is False
    assert report["mismatches"]["ETH/USDT"]["rows"] == 7


def test_membership_is_explicitly_static() -> None:
    membership = build_static_membership(["BTC/USDT", "ETH/USDT"])
    assert list(membership.columns) == ["pair", "effective_at"]
    assert membership["effective_at"].iloc[0].endswith("Z")
