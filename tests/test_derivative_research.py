import pandas as pd

from research.evaluation.derivative_features import add_basis_oi_features, funding_policy
from research.evaluation.derivative_manifest import audit
from research.evaluation.liquidation_events import validate_events


def test_basis_oi_features_are_backward_only_and_nullable():
    candles = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=3, freq="h"), "close": [100, 101, 99]})
    mark = pd.DataFrame({"date": candles.date, "close": [100, 101.2, 99.1]})
    index = pd.DataFrame({"date": candles.date, "close": [100, 101, 99]})
    oi = pd.DataFrame({"date": candles.date, "open_interest_amount": [10, 11, 9]})
    out = add_basis_oi_features(candles, mark=mark, index=index, open_interest=oi)
    assert out["basis"].notna().all()
    assert out["oi_change_pct"].isna().iloc[0]
    assert bool(out["basis_oi_trend_long"].iloc[1])
    assert bool(out["basis_oi_capitulation"].iloc[2])


def test_funding_policy_fails_closed_for_missing_values():
    funding = pd.Series([-.001, .001, None, .02])
    assert funding_policy(funding, side="long").tolist() == [True, False, False, False]
    assert funding_policy(funding, side="short").tolist() == [False, True, False, False]


def test_liquidation_validation_requires_provenance_fields():
    report = validate_events(pd.DataFrame({"timestamp": ["2025-01-01T00:00:00Z"], "source": ["fixture"]}))
    assert report["valid"] is False
    assert report["historical_backtest_ready"] is False


def test_manifest_reports_derivative_files_outside_reference_window(tmp_path):
    ohlcv = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=2, freq="h"), "close": [1, 2]})
    ohlcv_path = tmp_path / "BTC_USDT-1h.feather"
    ohlcv.to_feather(ohlcv_path)
    funding = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=2, freq="8h"), "funding_rate": [0, 0]})
    funding.to_feather(tmp_path / "BTC_USDT-1h-funding_rate.feather")
    report = audit(tmp_path, ohlcv_file=ohlcv_path)
    assert report["outside_window_types"] == ["funding_rate"]
