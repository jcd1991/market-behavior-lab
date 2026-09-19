"""Regime router with a negative-jump entry veto."""

from __future__ import annotations

from freqtrade.strategy import DecimalParameter, IntParameter
from pandas import DataFrame

from RegimeRouted import RegimeRouted
from advanced_strategy_helpers import signed_jump_score


class JumpAwareRegimeRouted(RegimeRouted):
    buy_jump_window = IntParameter(24, 168, default=48, space="buy", optimize=False, load=True)
    buy_jump_veto = DecimalParameter(1.0, 5.0, default=3.0, decimals=1, space="buy", optimize=False, load=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        frame["jump_score"] = signed_jump_score(frame["close"], int(self.buy_jump_window.value))
        return frame

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_entry_trend(dataframe, metadata)
        stress = frame["jump_score"] <= -float(self.buy_jump_veto.value)
        frame.loc[stress, ["enter_long", "enter_short"]] = 0
        return frame
