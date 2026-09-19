"""5-minute signals requiring independent 15-minute trend confirmation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.strategy import IntParameter, IStrategy
from pandas import DataFrame

try:
    from user_data.strategies.research_strategy_helpers import utc_series
except ModuleNotFoundError:
    from research_strategy_helpers import utc_series


class MultiTimeframeConfirmation(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 600
    stoploss = -0.08
    minimal_roi = {"0": 100.0}

    buy_mtf_fast = IntParameter(6, 36, default=12, space="buy", optimize=True)
    buy_mtf_slow = IntParameter(24, 120, default=48, space="buy", optimize=True)
    buy_mtf_confirm_fast = IntParameter(4, 24, default=12, space="buy", optimize=True)
    buy_mtf_confirm_slow = IntParameter(12, 72, default=36, space="buy", optimize=True)

    def informative_pairs(self):
        try:
            return [(pair, "15m") for pair in self.dp.current_whitelist()]
        except Exception:
            return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["mtf_fast"] = ta.EMA(dataframe, timeperiod=int(self.buy_mtf_fast.value))
        dataframe["mtf_slow"] = ta.EMA(dataframe, timeperiod=int(self.buy_mtf_slow.value))
        dataframe["mtf_confirm_fast"] = np.nan
        dataframe["mtf_confirm_slow"] = np.nan
        try:
            higher = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe="15m")
        except Exception:
            higher = None
        if higher is not None and not higher.empty:
            higher = higher.copy()
            higher["__date"] = utc_series(higher["date"])
            higher["mtf_confirm_fast"] = ta.EMA(higher, timeperiod=int(self.buy_mtf_confirm_fast.value))
            higher["mtf_confirm_slow"] = ta.EMA(higher, timeperiod=int(self.buy_mtf_confirm_slow.value))
            left = dataframe.copy()
            left["__date"] = utc_series(left["date"])
            right = higher[["__date", "mtf_confirm_fast", "mtf_confirm_slow"]].dropna(subset=["__date"]).sort_values("__date")
            merged = pd.merge_asof(left.sort_values("__date"), right, on="__date", direction="backward", suffixes=("", "_higher"))
            dataframe["mtf_confirm_fast"] = merged["mtf_confirm_fast_higher"].to_numpy() if "mtf_confirm_fast_higher" in merged else merged["mtf_confirm_fast"].to_numpy()
            dataframe["mtf_confirm_slow"] = merged["mtf_confirm_slow_higher"].to_numpy() if "mtf_confirm_slow_higher" in merged else merged["mtf_confirm_slow"].to_numpy()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        higher_up = dataframe["mtf_confirm_fast"].gt(dataframe["mtf_confirm_slow"])
        higher_down = dataframe["mtf_confirm_fast"].lt(dataframe["mtf_confirm_slow"])
        dataframe["enter_long"] = (dataframe["mtf_fast"].gt(dataframe["mtf_slow"]) & higher_up).astype(int)
        dataframe["enter_short"] = (dataframe["mtf_fast"].lt(dataframe["mtf_slow"]) & higher_down).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "mtf_confirmed_long", np.where(dataframe["enter_short"], "mtf_confirmed_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["mtf_fast"].lt(dataframe["mtf_slow"]).astype(int)
        dataframe["exit_short"] = dataframe["mtf_fast"].gt(dataframe["mtf_slow"]).astype(int)
        dataframe["exit_tag"] = "mtf_fast_slow_exit"
        return dataframe


class MultiTimeframeConfirmationSpot(MultiTimeframeConfirmation):
    """Long-only spot equivalent of the benchmark."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "mtf_confirmed_long", "")
        return dataframe
