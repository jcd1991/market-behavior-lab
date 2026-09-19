"""Cross-sectional momentum that trades only above an execution-cost floor."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

try:
    from user_data.strategies.research_strategy_helpers import scheduled_bars, utc_series
except ModuleNotFoundError:
    from research_strategy_helpers import scheduled_bars, utc_series


class CostAwareMomentumGate(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 180
    stoploss = -0.14
    minimal_roi = {"0": 100.0}

    buy_cag_lookback = IntParameter(24, 240, default=72, space="buy", optimize=True)
    buy_cag_rebalance_hours = IntParameter(4, 48, default=24, space="buy", optimize=True)
    buy_cag_signal_floor = DecimalParameter(0.001, 0.10, default=0.02, decimals=3, space="buy", optimize=True)
    buy_cag_fee = DecimalParameter(0.0001, 0.0030, default=0.0010, decimals=4, space="buy", optimize=False)
    buy_cag_spread = DecimalParameter(0.0000, 0.0100, default=0.0010, decimals=4, space="buy", optimize=False)
    buy_cag_slippage = DecimalParameter(0.0000, 0.0200, default=0.0010, decimals=4, space="buy", optimize=False)
    buy_cag_safety = DecimalParameter(0.0000, 0.0200, default=0.0010, decimals=4, space="buy", optimize=False)

    def _median_return(self, dataframe: DataFrame) -> pd.Series:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        values = []
        lookback = int(self.buy_cag_lookback.value)
        for pair in pairs:
            try:
                frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
            except Exception:
                frame = None
            if frame is not None and not frame.empty:
                values.append(pd.Series(pd.to_numeric(frame["close"], errors="coerce").pct_change(lookback).to_numpy(), index=utc_series(frame["date"])))
        if not values:
            return pd.Series(np.nan, index=dataframe.index)
        target = pd.DatetimeIndex(utc_series(dataframe["date"]).to_numpy())
        return pd.concat(values, axis=1).median(axis=1).sort_index().reindex(target, method="ffill").set_axis(dataframe.index)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        dataframe["cag_edge"] = close.pct_change(int(self.buy_cag_lookback.value)) - self._median_return(dataframe)
        dataframe["cag_cost_floor"] = 2.0 * (float(self.buy_cag_fee.value) + float(self.buy_cag_spread.value) + float(self.buy_cag_slippage.value)) + float(self.buy_cag_safety.value)
        dataframe["cag_schedule"] = scheduled_bars(dataframe, int(self.buy_cag_rebalance_hours.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = np.maximum(float(self.buy_cag_signal_floor.value), dataframe["cag_cost_floor"])
        active = dataframe["cag_schedule"]
        dataframe["enter_long"] = (active & dataframe["cag_edge"].ge(threshold)).astype(int)
        dataframe["enter_short"] = (active & dataframe["cag_edge"].le(-threshold)).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "cost_edge_long", np.where(dataframe["enter_short"], "cost_edge_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["cag_edge"].le(0).astype(int)
        dataframe["exit_short"] = dataframe["cag_edge"].ge(0).astype(int)
        dataframe["exit_tag"] = "cost_edge_lost"
        return dataframe
