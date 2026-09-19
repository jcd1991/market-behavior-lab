"""Long-only volatility/crash-protection lane for spot or unlevered futures."""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

try:
    from user_data.strategies.market_context import reference_pair
except ModuleNotFoundError:  # Direct strategy-module imports in focused tests.
    from market_context import reference_pair
try:
    from user_data.strategies.research_strategy_helpers import merge_close
except ModuleNotFoundError:  # Direct strategy-module imports in focused tests.
    from research_strategy_helpers import merge_close


class VolatilityCrashGuard(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 220
    stoploss = -0.12
    minimal_roi = {"0": 100.0}

    buy_vcg_market_ema = IntParameter(48, 240, default=120, space="buy", optimize=True)
    buy_vcg_vol_window = IntParameter(12, 96, default=24, space="buy", optimize=True)
    buy_vcg_vol_max = DecimalParameter(0.01, 0.30, default=0.10, decimals=3, space="buy", optimize=True)
    buy_vcg_pair_ema = IntParameter(12, 120, default=48, space="buy", optimize=True)
    sell_vcg_vol_exit = DecimalParameter(0.03, 0.50, default=0.16, decimals=3, space="sell", optimize=True)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._market_pair = reference_pair("BTC", config)

    def informative_pairs(self):
        return [(self._market_pair, self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        dataframe["vcg_pair_ema"] = ta.EMA(dataframe, timeperiod=int(self.buy_vcg_pair_ema.value))
        try:
            market = self.dp.get_pair_dataframe(pair=self._market_pair, timeframe=self.timeframe)
        except Exception:
            market = None
        if market is None or market.empty:
            dataframe["vcg_market_close"] = np.nan
            dataframe["vcg_market_ema"] = np.nan
            dataframe["vcg_market_vol"] = np.nan
            return dataframe
        merged = merge_close(dataframe, market, "vcg_market_close")
        market_close = pd.to_numeric(merged["vcg_market_close"], errors="coerce")
        win = int(self.buy_vcg_vol_window.value)
        dataframe["vcg_market_close"] = market_close.to_numpy()
        dataframe["vcg_market_ema"] = market_close.ewm(span=int(self.buy_vcg_market_ema.value), adjust=False, min_periods=int(self.buy_vcg_market_ema.value)).mean().to_numpy()
        dataframe["vcg_market_vol"] = market_close.pct_change().rolling(win, min_periods=win).std().mul(np.sqrt(24 * 365)).to_numpy()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        allowed = dataframe["vcg_market_close"].gt(dataframe["vcg_market_ema"]) & dataframe["vcg_market_vol"].le(float(self.buy_vcg_vol_max.value))
        dataframe["enter_long"] = (allowed & dataframe["close"].gt(dataframe["vcg_pair_ema"])).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "volatility_guard_long", "")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = (
            dataframe["close"].lt(dataframe["vcg_pair_ema"])
            | dataframe["vcg_market_close"].lt(dataframe["vcg_market_ema"])
            | dataframe["vcg_market_vol"].gt(float(self.sell_vcg_vol_exit.value))
        ).astype(int)
        dataframe["exit_tag"] = "volatility_or_trend_guard"
        return dataframe
