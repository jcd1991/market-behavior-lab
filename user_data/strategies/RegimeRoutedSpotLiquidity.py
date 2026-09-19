"""Liquidity-aware, spot-only research sleeve for U.S.-venue validation."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from freqtrade.strategy import BooleanParameter, DecimalParameter

from RegimeRoutedSpot import RegimeRoutedSpot


class RegimeRoutedSpotLiquidity(RegimeRoutedSpot):
    """RegimeRoutedSpot with explicit liquidity, volatility, and session controls.

    This is a research lane, not a claim that these filters create an edge.
    It intentionally uses only spot OHLCV for execution decisions. Futures
    funding, basis, mark, index, and open-interest features remain absent.
    """

    buy_rrsl_min_volume_ratio = DecimalParameter(
        0.10, 1.50, default=0.35, decimals=2, space="buy", optimize=True, load=True
    )
    buy_rrsl_max_atr_pct = DecimalParameter(
        0.02, 0.20, default=0.12, decimals=3, space="buy", optimize=True, load=True
    )
    buy_rrsl_session_sizing_enabled = BooleanParameter(
        default=True, space="buy", optimize=False, load=True
    )
    buy_rrsl_off_session_mult = DecimalParameter(
        0.50, 1.00, default=0.80, decimals=2, space="buy", optimize=True, load=True
    )
    buy_rrsl_weekend_mult = DecimalParameter(
        0.50, 1.00, default=0.70, decimals=2, space="buy", optimize=True, load=True
    )

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        volume = pd.to_numeric(dataframe.get("volume"), errors="coerce")
        close = pd.to_numeric(dataframe.get("close"), errors="coerce")
        high = pd.to_numeric(dataframe.get("high"), errors="coerce")
        low = pd.to_numeric(dataframe.get("low"), errors="coerce")

        volume_median = volume.replace(0.0, np.nan).rolling(48, min_periods=24).median()
        dataframe["rrsl_volume_ratio"] = volume / volume_median.replace(0.0, np.nan)
        tr = pd.concat(
            [(high - low).abs(), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
            axis=1,
        ).max(axis=1)
        dataframe["rrsl_atr_pct"] = (
            tr.rolling(24, min_periods=12).mean() / close.replace(0.0, np.nan)
        )
        dataframe["rrsl_liquid"] = (
            dataframe["rrsl_volume_ratio"] >= float(self.buy_rrsl_min_volume_ratio.value)
        ) & (
            dataframe["rrsl_atr_pct"] <= float(self.buy_rrsl_max_atr_pct.value)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        liquid = dataframe.get("rrsl_liquid", pd.Series(False, index=dataframe.index)).fillna(False)
        for column in ("enter_long", "enter_short"):
            if column in dataframe.columns:
                dataframe.loc[~liquid.astype(bool), column] = 0
        return dataframe

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        stake = super().custom_stake_amount(
            pair=pair,
            current_time=current_time,
            current_rate=current_rate,
            proposed_stake=proposed_stake,
            min_stake=min_stake,
            max_stake=max_stake,
            leverage=leverage,
            entry_tag=entry_tag,
            side=side,
            **kwargs,
        )
        if not bool(self.buy_rrsl_session_sizing_enabled.value):
            return stake
        multiplier = 1.0 if 13 <= current_time.hour < 20 else float(self.buy_rrsl_off_session_mult.value)
        if current_time.weekday() >= 5:
            multiplier *= float(self.buy_rrsl_weekend_mult.value)
        sized = min(float(max_stake), max(0.0, float(stake) * multiplier))
        if min_stake is not None and sized < float(min_stake):
            return 0.0
        return sized
