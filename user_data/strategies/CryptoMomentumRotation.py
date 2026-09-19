"""Independent cross-sectional momentum research lane.

This strategy intentionally does not use the regime router.  It ranks each
pair against the contemporaneous universe median and trades only on scheduled
UTC rebalance bars.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

try:
    from user_data.strategies.research_strategy_helpers import scheduled_bars, utc_series
except ModuleNotFoundError:  # Direct strategy-module imports in focused tests.
    from research_strategy_helpers import scheduled_bars, utc_series


class CryptoMomentumRotation(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 220
    stoploss = -0.12
    minimal_roi = {"0": 100.0}

    buy_mom_lookback = IntParameter(12, 240, default=72, space="buy", optimize=True)
    buy_mom_rebalance_hours = IntParameter(4, 48, default=24, space="buy", optimize=True)
    buy_mom_edge = DecimalParameter(0.005, 0.20, default=0.025, decimals=3, space="buy", optimize=True)
    buy_mom_atr_max = DecimalParameter(0.02, 0.30, default=0.12, decimals=3, space="buy", optimize=True)
    sell_mom_exit_edge = DecimalParameter(-0.02, 0.02, default=0.0, decimals=3, space="sell", optimize=True)

    def informative_pairs(self):
        return []

    def _universe_median(self, dataframe: DataFrame) -> pd.Series:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        lookback = int(self.buy_mom_lookback.value)
        series: list[pd.Series] = []
        for pair in pairs:
            try:
                frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
            except Exception:
                frame = None
            if frame is None or frame.empty:
                continue
            dates = utc_series(frame["date"])
            close = pd.to_numeric(frame["close"], errors="coerce")
            series.append(pd.Series(close.pct_change(lookback).to_numpy(), index=dates))
        if not series:
            return pd.Series(np.nan, index=utc_series(dataframe["date"]))
        target = pd.DatetimeIndex(utc_series(dataframe["date"]).to_numpy())
        median = pd.concat(series, axis=1).median(axis=1).sort_index()
        return median.reindex(target, method="ffill").set_axis(dataframe.index)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        lookback = int(self.buy_mom_lookback.value)
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        dataframe["mom_return"] = close.pct_change(lookback)
        dataframe["mom_universe_median"] = self._universe_median(dataframe)
        dataframe["mom_edge"] = dataframe["mom_return"] - dataframe["mom_universe_median"]
        atr = pd.to_numeric(ta.ATR(dataframe, timeperiod=14), errors="coerce")
        dataframe["mom_atr_pct"] = atr / close.replace(0, np.nan)
        dataframe["mom_schedule"] = scheduled_bars(dataframe, int(self.buy_mom_rebalance_hours.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        edge = float(self.buy_mom_edge.value)
        valid = dataframe["mom_schedule"] & dataframe["mom_atr_pct"].le(float(self.buy_mom_atr_max.value))
        dataframe["enter_long"] = (valid & dataframe["mom_edge"].ge(edge)).astype(int)
        dataframe["enter_short"] = (valid & dataframe["mom_edge"].le(-edge)).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "mom_long", np.where(dataframe["enter_short"], "mom_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = float(self.sell_mom_exit_edge.value)
        dataframe["exit_long"] = dataframe["mom_edge"].le(threshold).astype(int)
        dataframe["exit_short"] = dataframe["mom_edge"].ge(-threshold).astype(int)
        dataframe["exit_tag"] = "momentum_edge_reversal"
        return dataframe
