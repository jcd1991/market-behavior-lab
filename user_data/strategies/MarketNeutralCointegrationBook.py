"""Freqtrade signal leg for a rolling, market-neutral residual book.

Freqtrade manages one pair at a time, so the actual two-leg hedge must be
orchestrated by a portfolio layer.  This strategy is intentionally explicit:
it emits long/short residual signals and exposes the hedge beta for that layer;
it does not claim that a single Freqtrade trade is a complete hedge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy


class MarketNeutralCointegrationBook(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 400
    minimal_roi = {"0": 100.0}
    stoploss = -0.08

    buy_coint_window = IntParameter(168, 360, default=240, space="buy", optimize=True)
    buy_coint_entry_z = DecimalParameter(1.4, 3.0, default=1.8, decimals=1, space="buy", optimize=True)
    buy_coint_min_corr = DecimalParameter(0.60, 0.95, default=0.75, decimals=2, space="buy", optimize=True)
    buy_coint_max_half_life = IntParameter(24, 240, default=120, space="buy", optimize=True)
    sell_coint_exit_z = DecimalParameter(0.0, 1.0, default=0.35, decimals=2, space="sell", optimize=True)

    def _reference_pair(self, pair: str) -> str:
        configured = self.config.get("cointegration_reference_pair")
        if configured and configured != pair:
            return configured
        base, rest = pair.split("/", 1)
        quote = rest.split(":", 1)[0]
        return f"BTC/{quote}:{quote}" if ":" in rest else f"BTC/{quote}"

    def informative_pairs(self):
        pairs = self.dp.current_whitelist() if self.dp else []
        return [(self._reference_pair(pair), self.timeframe) for pair in pairs]

    @staticmethod
    def _features(asset: DataFrame, reference: DataFrame, window: int) -> DataFrame:
        left = asset[["date", "close"]].copy()
        right = reference[["date", "close"]].rename(columns={"close": "reference_close"})
        left["date"] = pd.to_datetime(left["date"], utc=True)
        right["date"] = pd.to_datetime(right["date"], utc=True)
        merged = pd.merge_asof(left.sort_values("date"), right.sort_values("date"), on="date", direction="backward")
        y = np.log(pd.to_numeric(merged["close"], errors="coerce").replace(0, np.nan))
        x = np.log(pd.to_numeric(merged["reference_close"], errors="coerce").replace(0, np.nan))
        beta = (y.rolling(window).cov(x) / x.rolling(window).var().replace(0, np.nan)).clip(-5, 5)
        residual = y - beta * x
        mean = residual.rolling(window).mean()
        std = residual.rolling(window).std().replace(0, np.nan)
        lag = residual.shift(1)
        delta = residual.diff()
        slope = delta.rolling(window).cov(lag) / lag.rolling(window).var().replace(0, np.nan)
        half_life = (-np.log(2.0) / slope).where(slope < 0)
        return pd.DataFrame({
            "date": merged["date"],
            "mn_beta": beta,
            "mn_residual_z": (residual - mean) / std,
            "mn_corr": y.rolling(window).corr(x),
            "mn_half_life": half_life,
        })

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        for col in ("mn_beta", "mn_residual_z", "mn_corr", "mn_half_life"):
            dataframe[col] = np.nan
        pair = metadata["pair"]
        reference = self._reference_pair(pair)
        if self.dp and reference != pair:
            ref = self.dp.get_pair_dataframe(reference, self.timeframe)
            if ref is not None and not ref.empty:
                features = self._features(dataframe, ref, int(self.buy_coint_window.value))
                base = dataframe.drop(columns=["mn_beta", "mn_residual_z", "mn_corr", "mn_half_life"])
                merged = pd.merge_asof(
                    base.assign(__date=pd.to_datetime(base["date"], utc=True)).sort_values("__date"),
                    features.rename(columns={"date": "__date"}).sort_values("__date"),
                    on="__date", direction="backward",
                )
                for col in ("mn_beta", "mn_residual_z", "mn_corr", "mn_half_life"):
                    dataframe[col] = merged[col].to_numpy()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        valid = (
            dataframe["mn_corr"].ge(float(self.buy_coint_min_corr.value))
            & dataframe["mn_half_life"].between(0, int(self.buy_coint_max_half_life.value))
            & dataframe["volume"].gt(0)
        )
        dataframe["enter_long"] = (valid & dataframe["mn_residual_z"].le(-float(self.buy_coint_entry_z.value))).astype(int)
        dataframe["enter_short"] = (valid & dataframe["mn_residual_z"].ge(float(self.buy_coint_entry_z.value))).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "residual_long_leg", np.where(dataframe["enter_short"], "residual_short_leg", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_z = float(self.sell_coint_exit_z.value)
        dataframe["exit_long"] = dataframe["mn_residual_z"].ge(-exit_z).astype(int)
        dataframe["exit_short"] = dataframe["mn_residual_z"].le(exit_z).astype(int)
        dataframe["exit_tag"] = "residual_reversion"
        return dataframe
