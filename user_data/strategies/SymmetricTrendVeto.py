"""Directional trend lane with asymmetric long/short trailing-return vetoes."""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame


class SymmetricTrendVeto(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 100
    stoploss = -0.15
    minimal_roi = {"0": 100.0}

    buy_stv_lookback_hours = IntParameter(12, 72, default=24, space="buy", optimize=True)
    buy_stv_long_veto = DecimalParameter(0.01, 0.12, default=0.03, decimals=3, space="buy", optimize=True)
    buy_stv_short_veto = DecimalParameter(0.01, 0.12, default=0.03, decimals=3, space="buy", optimize=True)
    buy_stv_ema = IntParameter(12, 120, default=48, space="buy", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        dataframe["stv_return"] = close.pct_change(int(self.buy_stv_lookback_hours.value))
        dataframe["stv_ema"] = ta.EMA(dataframe, timeperiod=int(self.buy_stv_ema.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ret = dataframe["stv_return"]
        long_ok = ret.gt(-float(self.buy_stv_long_veto.value))
        short_ok = ret.lt(float(self.buy_stv_short_veto.value))
        dataframe["enter_long"] = (long_ok & dataframe["close"].gt(dataframe["stv_ema"])).astype(int)
        dataframe["enter_short"] = (short_ok & dataframe["close"].lt(dataframe["stv_ema"])).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "trend_long_veto_clear", np.where(dataframe["enter_short"], "trend_short_veto_clear", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["close"].lt(dataframe["stv_ema"]).astype(int)
        dataframe["exit_short"] = dataframe["close"].gt(dataframe["stv_ema"]).astype(int)
        dataframe["exit_tag"] = "trend_veto_ema_exit"
        return dataframe
