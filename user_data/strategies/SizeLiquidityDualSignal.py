"""Large/liquid momentum versus small/liquid-proxy reversal research lane."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

from research_strategy_helpers import scheduled_bars, utc_series


class SizeLiquidityDualSignal(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 240
    stoploss = -0.12
    minimal_roi = {"0": 100.0}

    buy_sld_momentum_window = IntParameter(24, 240, default=72, space="buy", optimize=True)
    buy_sld_reversal_window = IntParameter(2, 24, default=6, space="buy", optimize=True)
    buy_sld_schedule_hours = IntParameter(4, 48, default=24, space="buy", optimize=True)
    buy_sld_large_rank = DecimalParameter(0.60, 0.95, default=0.75, decimals=2, space="buy", optimize=True)
    buy_sld_small_rank = DecimalParameter(0.05, 0.40, default=0.25, decimals=2, space="buy", optimize=True)
    buy_sld_entry_return = DecimalParameter(0.005, 0.20, default=0.025, decimals=3, space="buy", optimize=True)
    sell_sld_exit_rank = DecimalParameter(0.35, 0.65, default=0.50, decimals=2, space="sell", optimize=True)

    def _universe(self, dataframe: DataFrame) -> dict[str, DataFrame]:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        result = {}
        for pair in pairs:
            try:
                frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
            except Exception:
                frame = None
            if frame is not None and not frame.empty:
                result[pair] = frame
        return result

    def _ranked_series(self, dataframe: DataFrame) -> tuple[pd.Series, pd.Series]:
        frames = self._universe(dataframe)
        if not frames:
            idx = utc_series(dataframe["date"])
            return pd.Series(np.nan, index=dataframe.index), pd.Series(np.nan, index=dataframe.index)
        mom = {}
        liq = {}
        mw = int(self.buy_sld_momentum_window.value)
        for pair, frame in frames.items():
            dates = utc_series(frame["date"])
            close = pd.to_numeric(frame["close"], errors="coerce")
            dollar_volume = close * pd.to_numeric(frame["volume"], errors="coerce")
            mom[pair] = pd.Series(close.pct_change(mw).to_numpy(), index=dates)
            liq[pair] = pd.Series(dollar_volume.rolling(24, min_periods=12).mean().to_numpy(), index=dates)
        target = pd.DatetimeIndex(utc_series(dataframe["date"]).to_numpy())
        mom_frame = pd.concat(mom, axis=1).sort_index()
        liq_frame = pd.concat(liq, axis=1).sort_index()
        pair = str(dataframe.attrs.get("pair", ""))
        # The caller supplies the current pair through attrs; otherwise use
        # the first available series for direct unit-level use.
        if pair not in mom_frame:
            pair = next(iter(mom_frame.columns))
        mom_rank = mom_frame.rank(axis=1, pct=True)[pair].reindex(target, method="ffill")
        liq_rank = liq_frame.rank(axis=1, pct=True)[pair].reindex(target, method="ffill")
        return mom_rank.set_axis(dataframe.index), liq_rank.set_axis(dataframe.index)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.attrs["pair"] = metadata.get("pair", "")
        dataframe["sld_momentum_rank"], dataframe["sld_liquidity_rank"] = self._ranked_series(dataframe)
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        dataframe["sld_recent_return"] = close.pct_change(int(self.buy_sld_reversal_window.value))
        dataframe["sld_schedule"] = scheduled_bars(dataframe, int(self.buy_sld_schedule_hours.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        scheduled = dataframe["sld_schedule"]
        large_long = dataframe["sld_liquidity_rank"].ge(float(self.buy_sld_large_rank.value)) & dataframe["sld_momentum_rank"].ge(float(self.buy_sld_large_rank.value)) & dataframe["sld_recent_return"].ge(float(self.buy_sld_entry_return.value))
        small_long = dataframe["sld_liquidity_rank"].le(float(self.buy_sld_small_rank.value)) & dataframe["sld_recent_return"].le(-float(self.buy_sld_entry_return.value))
        large_short = dataframe["sld_liquidity_rank"].ge(float(self.buy_sld_large_rank.value)) & dataframe["sld_momentum_rank"].le(float(self.buy_sld_small_rank.value)) & dataframe["sld_recent_return"].le(-float(self.buy_sld_entry_return.value))
        small_short = dataframe["sld_liquidity_rank"].le(float(self.buy_sld_small_rank.value)) & dataframe["sld_recent_return"].ge(float(self.buy_sld_entry_return.value))
        dataframe["enter_long"] = (scheduled & (large_long | small_long)).astype(int)
        dataframe["enter_short"] = (scheduled & (large_short | small_short)).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "size_liquidity_long", np.where(dataframe["enter_short"], "size_liquidity_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = float(self.sell_sld_exit_rank.value)
        dataframe["exit_long"] = dataframe["sld_momentum_rank"].le(threshold).astype(int)
        dataframe["exit_short"] = dataframe["sld_momentum_rank"].ge(threshold).astype(int)
        dataframe["exit_tag"] = "size_signal_reversal"
        return dataframe
