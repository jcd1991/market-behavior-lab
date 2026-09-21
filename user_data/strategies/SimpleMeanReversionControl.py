"""Clean-license mean-reversion control for Market Behavior Lab.

Original implementation, informed by the MIT-licensed public reference
project listed in docs/references.md.  This file is intentionally small and
keeps the control reproducible rather than importing third-party strategy
code.
"""

import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy
import freqtrade.vendor.qtpylib.indicators as qtpylib


class SimpleMeanReversionControl(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    startup_candle_count = 60
    can_short = False
    minimal_roi = {"0": 0.02, "240": 0.01, "720": 0}
    stoploss = -0.06
    trailing_stop = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bands = qtpylib.bollinger_bands(dataframe["close"], window=20, stds=2)
        dataframe["bb_lower"] = bands["lower"]
        dataframe["bb_mid"] = bands["mid"]
        dataframe["bb_upper"] = bands["upper"]
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["bb_lower"])
            & (dataframe["rsi"] < 35)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            ((dataframe["close"] > dataframe["bb_mid"]) | (dataframe["rsi"] > 60)),
            "exit_long",
        ] = 1
        return dataframe
