"""Long-only multi-horizon Donchian breakout research lane for spot."""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame


class BreakoutEnsembleSpot(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 220
    stoploss = -0.14
    minimal_roi = {"0": 100.0}

    buy_bes_votes = IntParameter(1, 4, default=3, space="buy", optimize=True)
    buy_bes_atr_max = DecimalParameter(0.03, 0.40, default=0.20, decimals=3, space="buy", optimize=True)
    buy_bes_breakout_buffer = DecimalParameter(0.0, 0.05, default=0.002, decimals=3, space="buy", optimize=True)
    sell_bes_ema = IntParameter(8, 96, default=24, space="sell", optimize=True)

    HORIZONS = (12, 24, 48, 96)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        buffer = float(self.buy_bes_breakout_buffer.value)
        for horizon in self.HORIZONS:
            dataframe[f"bes_upper_{horizon}"] = dataframe["high"].rolling(horizon, min_periods=horizon).max().shift(1)
        dataframe["bes_atr_pct"] = ta.ATR(dataframe, timeperiod=14) / dataframe["close"].replace(0, np.nan)
        dataframe["bes_ema"] = ta.EMA(dataframe, timeperiod=int(self.sell_bes_ema.value))
        upper = dataframe[[f"bes_upper_{horizon}" for horizon in self.HORIZONS]]
        dataframe["bes_votes"] = (dataframe["close"].to_numpy()[:, None] > upper.to_numpy() * (1.0 + buffer)).sum(axis=1)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        valid = dataframe["bes_atr_pct"].le(float(self.buy_bes_atr_max.value))
        dataframe["enter_long"] = (valid & dataframe["bes_votes"].ge(int(self.buy_bes_votes.value))).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "multi_horizon_breakout", "")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["close"].lt(dataframe["bes_ema"]).astype(int)
        dataframe["exit_tag"] = "ensemble_trend_exit"
        return dataframe
