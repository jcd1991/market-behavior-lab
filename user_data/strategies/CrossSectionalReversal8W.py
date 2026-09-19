"""Weekly cross-sectional reversal with a high-volatility condition."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

try:
    from user_data.strategies.research_strategy_helpers import scheduled_bars, utc_series
except ModuleNotFoundError:
    from research_strategy_helpers import scheduled_bars, utc_series


class CrossSectionalReversal8W(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 380
    stoploss = -0.18
    minimal_roi = {"0": 100.0}

    buy_csr8w_formation_bars = IntParameter(240, 480, default=336, space="buy", optimize=True)
    buy_csr8w_rebalance_hours = IntParameter(120, 336, default=168, space="buy", optimize=True)
    buy_csr8w_rank_edge = DecimalParameter(0.05, 0.35, default=0.20, decimals=2, space="buy", optimize=True)
    buy_csr8w_vol_percentile = DecimalParameter(0.50, 0.95, default=0.75, decimals=2, space="buy", optimize=True)
    buy_csr8w_max_liquidity_rank = DecimalParameter(0.50, 1.00, default=0.90, decimals=2, space="buy", optimize=True)

    def _universe(self, dataframe: DataFrame) -> dict[str, DataFrame]:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        frames = {}
        for pair in pairs:
            try:
                frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
            except Exception:
                frame = None
            if frame is not None and not frame.empty:
                frames[pair] = frame
        return frames

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.attrs["pair"] = metadata.get("pair", "")
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        lookback = int(self.buy_csr8w_formation_bars.value)
        dataframe["csr8w_return"] = close.pct_change(lookback)
        dataframe["csr8w_vol"] = close.pct_change().rolling(lookback, min_periods=lookback // 2).std()
        dataframe["csr8w_liquidity"] = (close * pd.to_numeric(dataframe["volume"], errors="coerce")).rolling(42, min_periods=14).mean()

        frames = self._universe(dataframe)
        target = pd.DatetimeIndex(utc_series(dataframe["date"]).to_numpy())
        returns: dict[str, pd.Series] = {}
        vols: dict[str, pd.Series] = {}
        liquidities: dict[str, pd.Series] = {}
        for pair, frame in frames.items():
            idx = utc_series(frame["date"])
            px = pd.to_numeric(frame["close"], errors="coerce")
            vol = px.pct_change().rolling(lookback, min_periods=lookback // 2).std()
            liq = (px * pd.to_numeric(frame["volume"], errors="coerce")).rolling(42, min_periods=14).mean()
            returns[pair] = pd.Series(px.pct_change(lookback).to_numpy(), index=idx)
            vols[pair] = pd.Series(vol.to_numpy(), index=idx)
            liquidities[pair] = pd.Series(liq.to_numpy(), index=idx)
        if returns:
            matrix = pd.concat(returns, axis=1).sort_index()
            vol_matrix = pd.concat(vols, axis=1).sort_index()
            liq_matrix = pd.concat(liquidities, axis=1).sort_index()
            pair = str(metadata.get("pair", ""))
            if pair not in matrix:
                pair = next(iter(matrix.columns))
            dataframe["csr8w_rank"] = matrix.rank(axis=1, pct=True)[pair].reindex(target, method="ffill").set_axis(dataframe.index)
            dataframe["csr8w_vol_rank"] = vol_matrix.rank(axis=1, pct=True)[pair].reindex(target, method="ffill").set_axis(dataframe.index)
            dataframe["csr8w_liq_rank"] = liq_matrix.rank(axis=1, pct=True)[pair].reindex(target, method="ffill").set_axis(dataframe.index)
        else:
            dataframe["csr8w_rank"] = np.nan
            dataframe["csr8w_vol_rank"] = np.nan
            dataframe["csr8w_liq_rank"] = np.nan
        dates = utc_series(dataframe["date"])
        rebalance_hours = int(self.buy_csr8w_rebalance_hours.value)
        dataframe["csr8w_schedule"] = (
            dates.dt.dayofweek.eq(0) & dates.dt.hour.eq(0)
            if rebalance_hours >= 120
            else scheduled_bars(dataframe, rebalance_hours)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        edge = float(self.buy_csr8w_rank_edge.value)
        active = dataframe["csr8w_schedule"] & dataframe["csr8w_vol_rank"].ge(float(self.buy_csr8w_vol_percentile.value)) & dataframe["csr8w_liq_rank"].le(float(self.buy_csr8w_max_liquidity_rank.value))
        dataframe["enter_long"] = (active & dataframe["csr8w_rank"].le(edge)).astype(int)
        dataframe["enter_short"] = (active & dataframe["csr8w_rank"].ge(1.0 - edge)).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "reversal_loser", np.where(dataframe["enter_short"], "reversal_winner", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["csr8w_rank"].ge(0.50).astype(int)
        dataframe["exit_short"] = dataframe["csr8w_rank"].le(0.50).astype(int)
        dataframe["exit_tag"] = "reversal_rank_mean"
        return dataframe
