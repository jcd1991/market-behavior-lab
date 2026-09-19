"""Lower-turnover scheduled portfolio rotation lane."""

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


class ScheduledPortfolioRotation(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 260
    stoploss = -0.15
    minimal_roi = {"0": 100.0}

    buy_spr_lookback = IntParameter(6, 120, default=30, space="buy", optimize=True)
    buy_spr_schedule_hours = IntParameter(12, 168, default=48, space="buy", optimize=True)
    buy_spr_edge = DecimalParameter(0.01, 0.30, default=0.04, decimals=3, space="buy", optimize=True)
    buy_spr_atr_max = DecimalParameter(0.02, 0.35, default=0.16, decimals=3, space="buy", optimize=True)
    sell_spr_edge = DecimalParameter(-0.05, 0.05, default=-0.01, decimals=3, space="sell", optimize=True)

    def informative_pairs(self):
        return []

    def _median_return(self, dataframe: DataFrame) -> DataFrame:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        lb = int(self.buy_spr_lookback.value)
        date_index = utc_series(dataframe["date"])
        values = []
        for pair in pairs:
            try:
                frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
            except Exception:
                frame = None
            if frame is not None and not frame.empty:
                values.append(pd.Series(frame["close"].pct_change(lb).to_numpy(), index=utc_series(frame["date"])))
        if not values:
            return pd.Series(np.nan, index=date_index)
        target = pd.DatetimeIndex(date_index.to_numpy())
        median = pd.concat(values, axis=1).median(axis=1).sort_index()
        return median.reindex(target, method="ffill").set_axis(dataframe.index)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = dataframe["close"].astype(float)
        dataframe["spr_return"] = close.pct_change(int(self.buy_spr_lookback.value))
        dataframe["spr_median_return"] = self._median_return(dataframe)
        dataframe["spr_edge"] = dataframe["spr_return"] - dataframe["spr_median_return"]
        dataframe["spr_atr_pct"] = ta.ATR(dataframe, timeperiod=14) / close.replace(0, np.nan)
        dataframe["spr_schedule"] = scheduled_bars(dataframe, int(self.buy_spr_schedule_hours.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = (
            dataframe["spr_schedule"]
            & dataframe["spr_edge"].ge(float(self.buy_spr_edge.value))
            & dataframe["spr_atr_pct"].le(float(self.buy_spr_atr_max.value))
        ).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "scheduled_rotation", "")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["spr_edge"].le(float(self.sell_spr_edge.value)).astype(int)
        dataframe["exit_tag"] = "rotation_rank_loss"
        return dataframe
