"""Fixed multi-horizon trend plus short-horizon reversal score."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame


class MultiHorizonTrendReversal(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 220
    stoploss = -0.12
    minimal_roi = {"0": 100.0}

    buy_mht_trend_weight = DecimalParameter(0.50, 0.95, default=0.75, decimals=2, space="buy", optimize=True)
    buy_mht_entry_score = DecimalParameter(0.01, 0.50, default=0.08, decimals=3, space="buy", optimize=True)
    buy_mht_reversal_window = IntParameter(1, 24, default=6, space="buy", optimize=True)
    sell_mht_exit_score = DecimalParameter(-0.10, 0.10, default=0.0, decimals=3, space="sell", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        trend = (close.pct_change(72) + close.pct_change(168)) / 2.0
        reversal = -close.pct_change(int(self.buy_mht_reversal_window.value))
        trend_scale = trend.rolling(168, min_periods=72).std(ddof=0).replace(0, np.nan)
        rev_scale = reversal.rolling(72, min_periods=24).std(ddof=0).replace(0, np.nan)
        trend_z = trend / trend_scale
        reversal_z = reversal / rev_scale
        weight = float(self.buy_mht_trend_weight.value)
        dataframe["mht_score"] = weight * trend_z + (1.0 - weight) * reversal_z
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        score = float(self.buy_mht_entry_score.value)
        dataframe["enter_long"] = dataframe["mht_score"].ge(score).astype(int)
        dataframe["enter_short"] = dataframe["mht_score"].le(-score).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "multi_horizon_long", np.where(dataframe["enter_short"], "multi_horizon_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = float(self.sell_mht_exit_score.value)
        dataframe["exit_long"] = dataframe["mht_score"].le(threshold).astype(int)
        dataframe["exit_short"] = dataframe["mht_score"].ge(-threshold).astype(int)
        dataframe["exit_tag"] = "multi_horizon_score_exit"
        return dataframe
