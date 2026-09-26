"""Breakout spot lane with BTC crash-state sizing and entry suppression."""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.strategy import DecimalParameter, IntParameter
from pandas import DataFrame

from BreakoutEnsembleSpot import BreakoutEnsembleSpot
from market_context import reference_pair
from research_strategy_helpers import merge_close


class BreakoutCrashStateSpot(BreakoutEnsembleSpot):
    """Use a broad BTC state as a risk overlay, not as a new alpha signal."""

    buy_bcs_market_ema = IntParameter(48, 240, default=96, space="buy", optimize=False, load=True)
    buy_bcs_drawdown_window = IntParameter(96, 360, default=180, space="buy", optimize=False, load=True)
    buy_bcs_half_drawdown = DecimalParameter(0.05, 0.30, default=0.15, decimals=3, space="buy", optimize=False, load=True)
    buy_bcs_off_drawdown = DecimalParameter(0.15, 0.60, default=0.30, decimals=3, space="buy", optimize=False, load=True)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._market_pair = reference_pair("BTC", config)

    def informative_pairs(self):
        return [(self._market_pair, self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        try:
            market = self.dp.get_pair_dataframe(pair=self._market_pair, timeframe=self.timeframe)
        except Exception:
            market = None
        if market is None or market.empty:
            frame["bcs_market_close"] = np.nan
            frame["bcs_market_ema"] = np.nan
            frame["bcs_market_drawdown"] = np.nan
            frame["bcs_size_scale"] = 0.0
            return frame
        merged = merge_close(frame.drop(columns=["bcs_market_close", "bcs_market_ema", "bcs_market_drawdown", "bcs_size_scale"], errors="ignore"), market, "bcs_market_close")
        close = pd.to_numeric(merged["bcs_market_close"], errors="coerce")
        ema = ta.EMA(pd.DataFrame({"close": close}), timeperiod=int(self.buy_bcs_market_ema.value))
        peak = close.rolling(int(self.buy_bcs_drawdown_window.value), min_periods=int(self.buy_bcs_drawdown_window.value)).max()
        drawdown = close / peak.replace(0.0, np.nan) - 1.0
        scale = pd.Series(1.0, index=close.index)
        scale[close.le(ema).fillna(True)] = 0.0
        scale[drawdown.le(-float(self.buy_bcs_off_drawdown.value)).fillna(False)] = 0.0
        scale[drawdown.le(-float(self.buy_bcs_half_drawdown.value)).fillna(False) & scale.gt(0)] = 0.5
        frame["bcs_market_close"] = close.to_numpy()
        frame["bcs_market_ema"] = pd.to_numeric(ema, errors="coerce").to_numpy()
        frame["bcs_market_drawdown"] = drawdown.to_numpy()
        frame["bcs_size_scale"] = scale.to_numpy()
        return frame

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_entry_trend(dataframe, metadata)
        frame["enter_long"] = (frame["enter_long"].astype(bool) & frame["bcs_size_scale"].gt(0)).astype(int)
        frame["enter_tag"] = np.where(frame["enter_long"], "crash_state_breakout", "")
        return frame

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        try:
            frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            scale = float(frame.iloc[-1].get("bcs_size_scale", 0.0)) if frame is not None and not frame.empty else 0.0
        except Exception:
            scale = 0.0
        stake = float(proposed_stake) * max(0.0, min(1.0, scale))
        if min_stake is not None and stake > 0:
            stake = max(float(min_stake), stake)
        return min(float(max_stake), stake) if max_stake is not None else stake
