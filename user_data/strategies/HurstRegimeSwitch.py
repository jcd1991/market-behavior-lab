"""OHLCV-only Hurst regime switch research lane.

Inspired by research comparing momentum in persistent regimes with mean
reversion in anti-persistent regimes. It is intentionally simple and
interpretable so the result can be compared with RegimeRouted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IStrategy, IntParameter

from hurst import rolling_hurst


class HurstRegimeSwitch(IStrategy):
    """Switch between trend continuation and mean reversion using rolling H."""

    INTERFACE_VERSION = 3
    can_short = True
    timeframe = "1h"
    startup_candle_count = 180
    stoploss = -0.08
    minimal_roi = {"0": 0.02}
    trailing_stop = False

    buy_hurst_window = IntParameter(96, 256, default=128, space="buy", optimize=True)
    buy_hurst_trend_min = DecimalParameter(0.52, 0.70, default=0.55, decimals=2, space="buy", optimize=True)
    buy_hurst_revert_max = DecimalParameter(0.30, 0.48, default=0.45, decimals=2, space="buy", optimize=True)
    buy_z_entry = DecimalParameter(1.0, 3.0, default=1.6, decimals=1, space="buy", optimize=True)
    buy_ema_fast = IntParameter(8, 32, default=16, space="buy", optimize=True)
    buy_ema_slow = IntParameter(32, 128, default=64, space="buy", optimize=True)
    sell_z_exit = DecimalParameter(0.0, 1.0, default=0.25, decimals=2, space="sell", optimize=True)

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        window = int(self.buy_hurst_window.value)
        dataframe["hurst"] = rolling_hurst(close, window)
        dataframe["hs_ema_fast"] = ta.EMA(dataframe, timeperiod=int(self.buy_ema_fast.value))
        dataframe["hs_ema_slow"] = ta.EMA(dataframe, timeperiod=int(self.buy_ema_slow.value))
        mean = close.rolling(window, min_periods=window).mean()
        std = close.rolling(window, min_periods=window).std(ddof=0).replace(0, np.nan)
        dataframe["hs_zscore"] = (close - mean) / std
        dataframe["hs_atr_pct"] = ta.ATR(dataframe, timeperiod=14) / close.replace(0, np.nan)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        h = pd.to_numeric(dataframe["hurst"], errors="coerce")
        z = pd.to_numeric(dataframe["hs_zscore"], errors="coerce")
        fast = pd.to_numeric(dataframe["hs_ema_fast"], errors="coerce")
        slow = pd.to_numeric(dataframe["hs_ema_slow"], errors="coerce")
        liquid = pd.to_numeric(dataframe["volume"], errors="coerce") > 0

        trend_long = liquid & (h >= float(self.buy_hurst_trend_min.value)) & (close > fast) & (fast > slow)
        trend_short = liquid & (h >= float(self.buy_hurst_trend_min.value)) & (close < fast) & (fast < slow)
        revert_long = liquid & (h <= float(self.buy_hurst_revert_max.value)) & (z <= -float(self.buy_z_entry.value))
        revert_short = liquid & (h <= float(self.buy_hurst_revert_max.value)) & (z >= float(self.buy_z_entry.value))

        dataframe["enter_long"] = (trend_long | revert_long).fillna(False).astype(int)
        dataframe["enter_short"] = (trend_short | revert_short).fillna(False).astype(int)
        dataframe["enter_tag"] = ""
        dataframe.loc[trend_long, "enter_tag"] = "hurst_trend_long"
        dataframe.loc[trend_short, "enter_tag"] = "hurst_trend_short"
        dataframe.loc[revert_long, "enter_tag"] = "hurst_revert_long"
        dataframe.loc[revert_short, "enter_tag"] = "hurst_revert_short"
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        z = pd.to_numeric(dataframe["hs_zscore"], errors="coerce")
        dataframe["exit_long"] = (z >= -float(self.sell_z_exit.value)).fillna(False).astype(int)
        dataframe["exit_short"] = (z <= float(self.sell_z_exit.value)).fillna(False).astype(int)
        dataframe["exit_tag"] = "hurst_mean_reverted"
        return dataframe
