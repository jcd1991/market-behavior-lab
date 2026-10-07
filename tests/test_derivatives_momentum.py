import numpy as np
import pandas as pd

from research.evaluation.derivatives_momentum import (
    DerivativesMomentumPolicy,
    prepare_features,
    simulate,
)


def _frame(periods: int = 240) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=periods, freq="min", tz="UTC")
    close = 100.0 * np.exp(np.linspace(0.0, 0.08, periods))
    return pd.DataFrame({
        "date": dates,
        "open": close,
        "high": close * 1.001,
        "low": close * 0.999,
        "close": close,
        "volume": [100.0] * periods,
    })


def test_prepare_features_uses_available_at_for_metrics() -> None:
    candles = _frame()
    mark = candles[["date", "close"]].rename(columns={"close": "mark_close"})
    index = candles[["date", "close"]].rename(columns={"close": "index_close"})
    metrics = pd.DataFrame({
        "date": candles.date[::5],
        "available_at": candles.date[::5] + pd.Timedelta(minutes=5),
        "open_interest": range(len(candles[::5])),
    })
    funding = pd.DataFrame({"date": candles.date[::5], "funding_rate": [0.0] * len(candles[::5])})
    result = prepare_features(candles, mark=mark, index=index, metrics=metrics, funding=funding)
    assert result["basis"].dropna().eq(0.0).all()
    assert result["open_interest"].notna().sum() > 0


def test_derivatives_momentum_is_causal_and_cost_aware() -> None:
    candles = _frame(720)
    mark = candles[["date", "close"]].rename(columns={"close": "mark_close"})
    index = candles[["date", "close"]].rename(columns={"close": "index_close"})
    metrics = pd.DataFrame({
        "date": candles.date[::5],
        "available_at": candles.date[::5] + pd.Timedelta(minutes=5),
        "open_interest": np.arange(len(candles[::5])) + 1000.0,
    })
    funding = pd.DataFrame({"date": candles.date[::5], "funding_rate": [0.0] * len(candles[::5])})
    features = prepare_features(candles, mark=mark, index=index, metrics=metrics, funding=funding)
    result = simulate({"BTC/USDT:USDT": features}, DerivativesMomentumPolicy(side="long", hold_bars=6))
    assert result["eligible"] is True
    assert result["accepted"] > 0
    assert result["cost_model"]["round_trip_bps"] == 18.0
