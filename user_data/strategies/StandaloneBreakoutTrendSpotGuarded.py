"""Spot breakout lane with an explicit broad-market trend guard."""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.strategy import BooleanParameter, IntParameter
from pandas import DataFrame

from StandaloneBreakoutTrendSpot import StandaloneBreakoutTrendSpot
from market_context import reference_pair
from research_strategy_helpers import merge_close


class StandaloneBreakoutTrendSpotGuarded(StandaloneBreakoutTrendSpot):
    """Long-only breakout that refuses entries below the BTC trend guard."""

    buy_sbt_guard_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_sbt_guard_ema = IntParameter(24, 240, default=96, space="buy", optimize=True, load=True)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._guard_pair = reference_pair("BTC", config)

    def informative_pairs(self):
        return [(self._guard_pair, self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        frame["sbt_guard_close"] = np.nan
        frame["sbt_guard_ema"] = np.nan
        try:
            market = self.dp.get_pair_dataframe(pair=self._guard_pair, timeframe=self.timeframe)
        except Exception:
            market = None
        if market is None or market.empty:
            return frame
        base = frame.drop(columns=["sbt_guard_close", "sbt_guard_ema"], errors="ignore")
        merged = merge_close(base, market, "__sbt_guard_close")
        guard_close = pd.to_numeric(merged["__sbt_guard_close"], errors="coerce")
        guard_ema = ta.EMA(guard_close, timeperiod=int(self.buy_sbt_guard_ema.value))
        frame["sbt_guard_close"] = guard_close.to_numpy()
        frame["sbt_guard_ema"] = np.asarray(guard_ema)
        return frame

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_entry_trend(dataframe, metadata)
        if bool(self.buy_sbt_guard_enabled.value):
            allowed = dataframe["sbt_guard_close"].gt(dataframe["sbt_guard_ema"])
            frame["enter_long"] = (frame["enter_long"].astype(bool) & allowed).astype(int)
            frame["enter_tag"] = np.where(frame["enter_long"], "guarded_breakout", "")
        return frame
