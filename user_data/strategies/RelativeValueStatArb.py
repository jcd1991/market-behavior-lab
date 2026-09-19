"""Fixed-leader residual/statistical-arbitrage research lane."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

try:
    from user_data.strategies.market_context import reference_pair
except ModuleNotFoundError:  # Direct strategy-module imports in focused tests.
    from market_context import reference_pair
try:
    from user_data.strategies.research_strategy_helpers import empty_signal_columns, merge_close
except ModuleNotFoundError:  # Direct strategy-module imports in focused tests.
    from research_strategy_helpers import empty_signal_columns, merge_close


class RelativeValueStatArb(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 260
    stoploss = -0.12
    minimal_roi = {"0": 100.0}

    buy_rva_beta_window = IntParameter(48, 240, default=96, space="buy", optimize=True)
    buy_rva_z_window = IntParameter(48, 240, default=96, space="buy", optimize=True)
    buy_rva_entry_z = DecimalParameter(1.0, 4.0, default=2.0, decimals=2, space="buy", optimize=True)
    buy_rva_exit_z = DecimalParameter(0.0, 1.5, default=0.35, decimals=2, space="sell", optimize=True)
    buy_rva_corr_min = DecimalParameter(0.0, 0.9, default=0.25, decimals=2, space="buy", optimize=True)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._leader = reference_pair("BTC", config)

    def informative_pairs(self):
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        return [(self._leader, self.timeframe)] if self._leader in pairs else []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        empty_signal_columns(dataframe, "rva")
        dataframe["rva_z"] = np.nan
        dataframe["rva_corr"] = np.nan
        pair = str(metadata.get("pair", ""))
        if pair == self._leader:
            return dataframe
        try:
            leader = self.dp.get_pair_dataframe(pair=self._leader, timeframe=self.timeframe)
        except Exception:
            leader = None
        if leader is None or leader.empty:
            return dataframe
        merged = merge_close(dataframe, leader, "rva_leader_close")
        y = np.log(pd.to_numeric(merged["close"], errors="coerce").replace(0, np.nan))
        x = np.log(pd.to_numeric(merged["rva_leader_close"], errors="coerce").replace(0, np.nan))
        window = int(self.buy_rva_beta_window.value)
        beta = y.rolling(window, min_periods=window // 2).cov(x) / x.rolling(window, min_periods=window // 2).var(ddof=0)
        residual = y - beta * x
        zwin = int(self.buy_rva_z_window.value)
        mean = residual.rolling(zwin, min_periods=zwin // 2).mean()
        std = residual.rolling(zwin, min_periods=zwin // 2).std(ddof=0).replace(0, np.nan)
        z = (residual - mean) / std
        corr = y.diff().rolling(window, min_periods=window // 2).corr(x.diff())
        merged["rva_z"] = z
        merged["rva_beta"] = beta
        merged["rva_corr"] = corr
        dataframe["rva_z"] = merged["rva_z"].to_numpy()
        dataframe["rva_beta"] = merged["rva_beta"].to_numpy()
        dataframe["rva_corr"] = merged["rva_corr"].to_numpy()
        dataframe["enter_long"] = (dataframe["rva_corr"].ge(float(self.buy_rva_corr_min.value)) & dataframe["rva_z"].le(-float(self.buy_rva_entry_z.value))).astype(int)
        dataframe["enter_short"] = (dataframe["rva_corr"].ge(float(self.buy_rva_corr_min.value)) & dataframe["rva_z"].ge(float(self.buy_rva_entry_z.value))).astype(int)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if "enter_long" not in dataframe:
            dataframe["enter_long"] = 0
        if "enter_short" not in dataframe:
            dataframe["enter_short"] = 0
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "residual_long", np.where(dataframe["enter_short"], "residual_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = float(self.buy_rva_exit_z.value)
        dataframe["exit_long"] = dataframe["rva_z"].ge(-threshold).astype(int)
        dataframe["exit_short"] = dataframe["rva_z"].le(threshold).astype(int)
        dataframe["exit_tag"] = "residual_mean_reversion"
        return dataframe
