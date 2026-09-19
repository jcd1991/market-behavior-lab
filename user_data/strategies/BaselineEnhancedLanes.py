"""Controlled enhancements for the public baseline strategy families.

Each class keeps the parent baseline's signals and exits, then adds one
project-specific gate inspired by an existing research lane.  These are
explicit comparison lanes, not tuned winners.
"""

from __future__ import annotations

import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy
from pandas import DataFrame

from BaselineEMAADX import BaselineEMAADX
from BaselineRSIBollinger import BaselineRSIBollinger
from MultiTimeframeConfirmation import MultiTimeframeConfirmation
from StandaloneBreakoutTrend import StandaloneBreakoutTrend


class BaselineRSIBollingerRegime(BaselineRSIBollinger):
    """Mean reversion aligned with the long/short side of a slow regime."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["rbb_regime_ema"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_long"] = (
            dataframe["enter_long"].astype(bool)
            & dataframe["close"].gt(dataframe["rbb_regime_ema"])
        ).astype(int)
        dataframe["enter_short"] = (
            dataframe["enter_short"].astype(bool)
            & dataframe["close"].lt(dataframe["rbb_regime_ema"])
        ).astype(int)
        dataframe["enter_tag"] = np.where(
            dataframe["enter_long"],
            "rsi_bb_regime_long",
            np.where(dataframe["enter_short"], "rsi_bb_regime_short", ""),
        )
        return dataframe


class BaselineRSIBollingerRegimeSpot(BaselineRSIBollingerRegime):
    """Long-only spot form of the regime-filtered mean-reversion lane."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "rsi_bb_regime_long", "")
        return dataframe


class BaselineEMAADXVolatility(BaselineEMAADX):
    """EMA/ADX trend following with the project's volatility/liquidity gate."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["eadx_atr_pct"] = ta.ATR(dataframe, timeperiod=14) / dataframe["close"].replace(0, np.nan)
        volume = dataframe["volume"].replace(0, np.nan)
        dataframe["eadx_volume_ratio"] = volume / volume.rolling(48, min_periods=24).median()
        dataframe["eadx_regime_ema"] = ta.EMA(dataframe, timeperiod=100)
        dataframe["eadx_allowed"] = (
            dataframe["eadx_atr_pct"].le(0.12)
            & dataframe["eadx_volume_ratio"].ge(0.35)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        allowed = dataframe["eadx_allowed"].fillna(False)
        dataframe["enter_long"] = (
            dataframe["enter_long"].astype(bool)
            & allowed
            & dataframe["close"].gt(dataframe["eadx_regime_ema"])
        ).astype(int)
        dataframe["enter_short"] = (
            dataframe["enter_short"].astype(bool)
            & allowed
            & dataframe["close"].lt(dataframe["eadx_regime_ema"])
        ).astype(int)
        dataframe["enter_tag"] = np.where(
            dataframe["enter_long"],
            "ema_adx_guarded_long",
            np.where(dataframe["enter_short"], "ema_adx_guarded_short", ""),
        )
        return dataframe


class BaselineEMAADXVolatilitySpot(BaselineEMAADXVolatility):
    """Long-only spot form of the gated EMA/ADX lane."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "ema_adx_guarded_long", "")
        return dataframe


class StandaloneBreakoutTrendRegime(StandaloneBreakoutTrend):
    """Donchian breakout with causal directional regime alignment."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["sbt_regime_ema"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_long"] = (
            dataframe["enter_long"].astype(bool)
            & dataframe["close"].gt(dataframe["sbt_regime_ema"])
        ).astype(int)
        dataframe["enter_short"] = (
            dataframe["enter_short"].astype(bool)
            & dataframe["close"].lt(dataframe["sbt_regime_ema"])
        ).astype(int)
        dataframe["enter_tag"] = np.where(
            dataframe["enter_long"],
            "donchian_regime_long",
            np.where(dataframe["enter_short"], "donchian_regime_short", ""),
        )
        return dataframe


class StandaloneBreakoutTrendRegimeSpot(StandaloneBreakoutTrendRegime):
    """Long-only spot form of the regime-aligned breakout lane."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "donchian_regime_long", "")
        return dataframe


class MultiTimeframeConfirmationVolatility(MultiTimeframeConfirmation):
    """Multi-timeframe confirmation with a conservative local volatility gate."""

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["mtf_atr_pct"] = ta.ATR(dataframe, timeperiod=14) / dataframe["close"].replace(0, np.nan)
        volume = dataframe["volume"].replace(0, np.nan)
        dataframe["mtf_volume_ratio"] = volume / volume.rolling(96, min_periods=48).median()
        dataframe["mtf_allowed"] = (
            dataframe["mtf_atr_pct"].le(0.08)
            & dataframe["mtf_volume_ratio"].ge(0.35)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        allowed = dataframe["mtf_allowed"].fillna(False)
        dataframe["enter_long"] = (dataframe["enter_long"].astype(bool) & allowed).astype(int)
        dataframe["enter_short"] = (dataframe["enter_short"].astype(bool) & allowed).astype(int)
        dataframe["enter_tag"] = np.where(
            dataframe["enter_long"],
            "mtf_guarded_long",
            np.where(dataframe["enter_short"], "mtf_guarded_short", ""),
        )
        return dataframe


class MultiTimeframeConfirmationVolatilitySpot(MultiTimeframeConfirmationVolatility):
    """Long-only spot form of the volatility-gated MTF lane."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "mtf_guarded_long", "")
        return dataframe
