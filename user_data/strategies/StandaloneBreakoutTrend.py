"""Simple Donchian/ATR trend-following lane without regime routing."""

from __future__ import annotations

import numpy as np
import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame


class StandaloneBreakoutTrend(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 220
    stoploss = -0.14
    minimal_roi = {"0": 100.0}

    buy_sbt_channel = IntParameter(12, 120, default=36, space="buy", optimize=True)
    buy_sbt_atr_max = DecimalParameter(0.03, 0.40, default=0.20, decimals=3, space="buy", optimize=True)
    buy_sbt_breakout_buffer = DecimalParameter(0.0, 0.05, default=0.002, decimals=3, space="buy", optimize=True)
    sell_sbt_ema = IntParameter(8, 96, default=24, space="sell", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        channel = int(self.buy_sbt_channel.value)
        dataframe["sbt_upper"] = dataframe["high"].rolling(channel, min_periods=channel).max().shift(1)
        dataframe["sbt_lower"] = dataframe["low"].rolling(channel, min_periods=channel).min().shift(1)
        dataframe["sbt_atr_pct"] = ta.ATR(dataframe, timeperiod=14) / dataframe["close"].replace(0, np.nan)
        dataframe["sbt_ema"] = ta.EMA(dataframe, timeperiod=int(self.sell_sbt_ema.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        buffer = float(self.buy_sbt_breakout_buffer.value)
        valid = dataframe["sbt_atr_pct"].le(float(self.buy_sbt_atr_max.value))
        dataframe["enter_long"] = (valid & dataframe["close"].gt(dataframe["sbt_upper"] * (1 + buffer))).astype(int)
        dataframe["enter_short"] = (valid & dataframe["close"].lt(dataframe["sbt_lower"] * (1 - buffer))).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "donchian_long", np.where(dataframe["enter_short"], "donchian_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["close"].lt(dataframe["sbt_ema"]).astype(int)
        dataframe["exit_short"] = dataframe["close"].gt(dataframe["sbt_ema"]).astype(int)
        dataframe["exit_tag"] = "trend_channel_exit"
        return dataframe
