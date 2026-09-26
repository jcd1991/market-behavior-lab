"""Long-only liquid cross-sectional momentum research lane.

The Freqtrade implementation is a pair-level expression of the ranking idea;
the shared-wallet evaluator in ``research/evaluation/recommended_lanes.py``
is the authoritative portfolio screen until point-in-time universe data is
available.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

try:
    from user_data.strategies.research_strategy_helpers import scheduled_bars, utc_series
except ModuleNotFoundError:
    from research_strategy_helpers import scheduled_bars, utc_series


class LiquidMomentumSpot(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 220
    stoploss = -0.12
    minimal_roi = {"0": 100.0}

    buy_lms_lookback = IntParameter(12, 168, default=42, space="buy", optimize=True)
    buy_lms_rebalance_bars = IntParameter(1, 12, default=6, space="buy", optimize=True)
    buy_lms_min_edge = DecimalParameter(0.0, 0.20, default=0.01, decimals=3, space="buy", optimize=True)
    buy_lms_volume_ratio_min = DecimalParameter(0.10, 2.0, default=0.50, decimals=2, space="buy", optimize=True)
    sell_lms_ema = IntParameter(12, 168, default=42, space="sell", optimize=True)

    def _universe_median(self, dataframe: DataFrame) -> pd.Series:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        lookback = int(self.buy_lms_lookback.value)
        series: list[pd.Series] = []
        for pair in pairs:
            try:
                frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
            except Exception:
                frame = None
            if frame is None or frame.empty:
                continue
            dates = utc_series(frame["date"])
            series.append(pd.Series(pd.to_numeric(frame["close"], errors="coerce").pct_change(lookback).to_numpy(), index=dates))
        if not series:
            return pd.Series(np.nan, index=dataframe.index)
        median = pd.concat(series, axis=1).median(axis=1).sort_index()
        target = pd.DatetimeIndex(utc_series(dataframe["date"]).to_numpy())
        return median.reindex(target, method="ffill").set_axis(dataframe.index)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        lookback = int(self.buy_lms_lookback.value)
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        quote_volume = close.abs() * pd.to_numeric(dataframe["volume"], errors="coerce").clip(lower=0.0)
        dataframe["lms_return"] = close.pct_change(lookback)
        dataframe["lms_universe_median"] = self._universe_median(dataframe)
        dataframe["lms_edge"] = dataframe["lms_return"] - dataframe["lms_universe_median"]
        dataframe["lms_volume_ratio"] = quote_volume / quote_volume.rolling(lookback, min_periods=max(6, lookback // 2)).median().replace(0.0, np.nan)
        dataframe["lms_ema"] = ta.EMA(dataframe, timeperiod=int(self.sell_lms_ema.value))
        dataframe["lms_schedule"] = scheduled_bars(dataframe, max(1, int(self.buy_lms_rebalance_bars.value) * 4))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        valid = dataframe["lms_schedule"] & dataframe["lms_volume_ratio"].ge(float(self.buy_lms_volume_ratio_min.value))
        valid &= dataframe["lms_edge"].ge(float(self.buy_lms_min_edge.value))
        valid &= dataframe["close"].gt(dataframe["lms_ema"])
        dataframe["enter_long"] = valid.astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "liquid_cross_sectional_momentum", "")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = (dataframe["lms_edge"].lt(0.0) | dataframe["close"].lt(dataframe["lms_ema"])).astype(int)
        dataframe["exit_tag"] = "momentum_rank_or_trend_exit"
        return dataframe
