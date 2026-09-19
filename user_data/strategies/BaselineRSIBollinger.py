"""Unchanged-style RSI plus Bollinger mean-reversion benchmark."""

from __future__ import annotations

import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class BaselineRSIBollinger(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 40
    stoploss = -0.10
    minimal_roi = {"0": 100.0}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bands = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_lower"] = bands["lowerband"]
        dataframe["bb_middle"] = bands["middleband"]
        dataframe["bb_upper"] = bands["upperband"]
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = (dataframe["close"].lt(dataframe["bb_lower"]) & dataframe["rsi"].lt(30)).astype(int)
        dataframe["enter_short"] = (dataframe["close"].gt(dataframe["bb_upper"]) & dataframe["rsi"].gt(70)).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "rsi_bb_long", np.where(dataframe["enter_short"], "rsi_bb_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["close"].ge(dataframe["bb_middle"]).astype(int)
        dataframe["exit_short"] = dataframe["close"].le(dataframe["bb_middle"]).astype(int)
        dataframe["exit_tag"] = "rsi_bb_middle"
        return dataframe


class BaselineRSIBollingerSpot(BaselineRSIBollinger):
    """Long-only spot equivalent of the benchmark."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "rsi_bb_long", "")
        return dataframe
