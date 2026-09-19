"""Transparent OHLCV factor ensemble layered on cross-sectional rotation."""

from __future__ import annotations

from freqtrade.strategy import DecimalParameter, IntParameter
from pandas import DataFrame

from CrossSectionalRotation import CrossSectionalRotation
from advanced_strategy_helpers import factor_ensemble


class CryptoFactorEnsemble(CrossSectionalRotation):
    buy_factor_lookback = IntParameter(12, 168, default=24, space="buy", optimize=False, load=True)
    buy_factor_min_score = DecimalParameter(-0.50, 0.50, default=-0.10, decimals=2, space="buy", optimize=False, load=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        lb = int(self.buy_factor_lookback.value)
        frame["factor_score"] = factor_ensemble(frame, (lb, lb * 3, lb * 7))
        return frame

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_entry_trend(dataframe, metadata)
        score = frame["factor_score"]
        frame.loc[score < float(self.buy_factor_min_score.value), "enter_long"] = 0
        frame.loc[score > -float(self.buy_factor_min_score.value), "enter_short"] = 0
        return frame
