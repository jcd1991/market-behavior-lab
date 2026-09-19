"""Cross-sectional momentum traded only when universe dispersion is elevated."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

from research_strategy_helpers import scheduled_bars, utc_series


class DispersionConditionedMomentum(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 180
    stoploss = -0.14
    minimal_roi = {"0": 100.0}

    buy_dcm_momentum_window = IntParameter(6, 72, default=24, space="buy", optimize=True)
    buy_dcm_schedule_hours = IntParameter(4, 48, default=24, space="buy", optimize=True)
    buy_dcm_rank_threshold = DecimalParameter(0.55, 0.95, default=0.75, decimals=2, space="buy", optimize=True)
    buy_dcm_dispersion_min = DecimalParameter(0.005, 0.30, default=0.04, decimals=3, space="buy", optimize=True)
    sell_dcm_rank_exit = DecimalParameter(0.35, 0.65, default=0.50, decimals=2, space="sell", optimize=True)

    def _cross_section(self, dataframe: DataFrame) -> tuple[pd.Series, pd.Series]:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        values = {}
        dates = {}
        window = int(self.buy_dcm_momentum_window.value)
        for pair in pairs:
            try:
                frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
            except Exception:
                frame = None
            if frame is None or frame.empty:
                continue
            idx = utc_series(frame["date"])
            values[pair] = pd.Series(pd.to_numeric(frame["close"], errors="coerce").pct_change(window).to_numpy(), index=idx)
            dates[pair] = idx
        target = pd.DatetimeIndex(utc_series(dataframe["date"]).to_numpy())
        if not values:
            return pd.Series(np.nan, index=dataframe.index), pd.Series(np.nan, index=dataframe.index)
        matrix = pd.concat(values, axis=1).sort_index()
        pair = str(dataframe.attrs.get("pair", ""))
        if pair not in matrix:
            pair = next(iter(matrix.columns))
        rank = matrix.rank(axis=1, pct=True)[pair].reindex(target, method="ffill")
        dispersion = matrix.std(axis=1, ddof=0).reindex(target, method="ffill")
        return rank.set_axis(dataframe.index), dispersion.set_axis(dataframe.index)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.attrs["pair"] = metadata.get("pair", "")
        dataframe["dcm_rank"], dataframe["dcm_dispersion"] = self._cross_section(dataframe)
        dataframe["dcm_schedule"] = scheduled_bars(dataframe, int(self.buy_dcm_schedule_hours.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        high = float(self.buy_dcm_rank_threshold.value)
        low = 1.0 - high
        active = dataframe["dcm_schedule"] & dataframe["dcm_dispersion"].ge(float(self.buy_dcm_dispersion_min.value))
        dataframe["enter_long"] = (active & dataframe["dcm_rank"].ge(high)).astype(int)
        dataframe["enter_short"] = (active & dataframe["dcm_rank"].le(low)).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "dispersion_momentum_long", np.where(dataframe["enter_short"], "dispersion_momentum_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = float(self.sell_dcm_rank_exit.value)
        dataframe["exit_long"] = dataframe["dcm_rank"].le(threshold).astype(int)
        dataframe["exit_short"] = dataframe["dcm_rank"].ge(threshold).astype(int)
        dataframe["exit_tag"] = "dispersion_rank_exit"
        return dataframe
