"""Short-horizon reversal gated by elevated realized volatility."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame


class VolatilityConditionedReversal(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 360
    stoploss = -0.08
    minimal_roi = {"0": 100.0}

    buy_vcr_z_window = IntParameter(48, 480, default=192, space="buy", optimize=True)
    buy_vcr_entry_z = DecimalParameter(1.0, 4.0, default=2.0, decimals=2, space="buy", optimize=True)
    buy_vcr_vol_window = IntParameter(24, 240, default=96, space="buy", optimize=True)
    buy_vcr_vol_ratio = DecimalParameter(1.0, 4.0, default=1.25, decimals=2, space="buy", optimize=True)
    sell_vcr_exit_z = DecimalParameter(0.0, 1.5, default=0.25, decimals=2, space="sell", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        ret = close.pct_change()
        zwin = int(self.buy_vcr_z_window.value)
        volwin = int(self.buy_vcr_vol_window.value)
        mean = ret.rolling(zwin, min_periods=zwin // 2).mean()
        std = ret.rolling(zwin, min_periods=zwin // 2).std(ddof=0).replace(0, np.nan)
        dataframe["vcr_return_z"] = (ret - mean) / std
        short_vol = ret.rolling(volwin, min_periods=volwin // 2).std(ddof=0)
        long_vol = short_vol.rolling(max(volwin * 3, 48), min_periods=volwin).median()
        dataframe["vcr_vol_ratio"] = short_vol / long_vol.replace(0, np.nan)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        active = dataframe["vcr_vol_ratio"].ge(float(self.buy_vcr_vol_ratio.value))
        dataframe["enter_long"] = (active & dataframe["vcr_return_z"].le(-float(self.buy_vcr_entry_z.value))).astype(int)
        dataframe["enter_short"] = (active & dataframe["vcr_return_z"].ge(float(self.buy_vcr_entry_z.value))).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "high_vol_reversal_long", np.where(dataframe["enter_short"], "high_vol_reversal_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = float(self.sell_vcr_exit_z.value)
        dataframe["exit_long"] = dataframe["vcr_return_z"].ge(-threshold).astype(int)
        dataframe["exit_short"] = dataframe["vcr_return_z"].le(threshold).astype(int)
        dataframe["exit_tag"] = "reversal_mean_reached"
        return dataframe
