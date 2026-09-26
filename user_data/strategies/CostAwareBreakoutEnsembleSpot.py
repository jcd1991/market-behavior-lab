"""Breakout ensemble with explicit liquidity and expected-move gates."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter
from pandas import DataFrame

from BreakoutEnsembleSpot import BreakoutEnsembleSpot


class CostAwareBreakoutEnsembleSpot(BreakoutEnsembleSpot):
    """Screen entries whose observed move is too small for modeled costs."""

    buy_bes_volume_ratio_min = DecimalParameter(0.10, 2.00, default=0.75, decimals=2, space="buy", optimize=False, load=True)
    buy_bes_min_move_bps = DecimalParameter(0.0, 100.0, default=20.0, decimals=1, space="buy", optimize=False, load=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        quote_volume = pd.to_numeric(frame["close"], errors="coerce").abs() * pd.to_numeric(frame["volume"], errors="coerce").clip(lower=0.0)
        window = max(6, min(self.HORIZONS))
        frame["bes_volume_ratio"] = quote_volume / quote_volume.rolling(window, min_periods=max(6, window // 2)).median().replace(0.0, np.nan)
        upper = frame[[f"bes_upper_{horizon}" for horizon in self.HORIZONS]].min(axis=1)
        frame["bes_move_bps"] = (frame["close"] / upper - 1.0) * 10000.0
        return frame

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_entry_trend(dataframe, metadata)
        allowed = dataframe["bes_volume_ratio"].ge(float(self.buy_bes_volume_ratio_min.value))
        allowed &= dataframe["bes_move_bps"].ge(float(self.buy_bes_min_move_bps.value))
        frame["enter_long"] = (frame["enter_long"].astype(bool) & allowed).astype(int)
        frame["enter_tag"] = np.where(frame["enter_long"], "cost_aware_breakout", "")
        return frame
