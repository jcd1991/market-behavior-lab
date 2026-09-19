"""Unchanged-style EMA trend-following benchmark with ADX confirmation."""

from __future__ import annotations

import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class BaselineEMAADX(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 60
    stoploss = -0.12
    minimal_roi = {"0": 100.0}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["plus_di"] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe["minus_di"] = ta.MINUS_DI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        trending = dataframe["adx"].gt(25)
        dataframe["enter_long"] = (trending & dataframe["ema_fast"].gt(dataframe["ema_slow"]) & dataframe["plus_di"].gt(dataframe["minus_di"])).astype(int)
        dataframe["enter_short"] = (trending & dataframe["ema_fast"].lt(dataframe["ema_slow"]) & dataframe["minus_di"].gt(dataframe["plus_di"])).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "ema_adx_long", np.where(dataframe["enter_short"], "ema_adx_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["ema_fast"].lt(dataframe["ema_slow"]).astype(int)
        dataframe["exit_short"] = dataframe["ema_fast"].gt(dataframe["ema_slow"]).astype(int)
        dataframe["exit_tag"] = "ema_cross_exit"
        return dataframe


class BaselineEMAADXSpot(BaselineEMAADX):
    """Long-only spot equivalent of the benchmark."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "ema_adx_long", "")
        return dataframe
