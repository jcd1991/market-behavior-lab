"""Time-series trend lane that stays in cash during unstable volatility."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from research_strategy_helpers import execution_cost_floor, quote_volume_features


class VolatilityManagedTrendCash(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 240
    minimal_roi = {"0": 100.0}
    stoploss = -0.12

    buy_vmt_fast = IntParameter(12, 72, default=24, space="buy", optimize=True)
    buy_vmt_slow = IntParameter(96, 360, default=168, space="buy", optimize=True)
    buy_vmt_min_score = DecimalParameter(0.20, 1.00, default=0.50, decimals=2, space="buy", optimize=True)
    buy_vmt_max_vol = DecimalParameter(0.40, 2.50, default=1.20, decimals=2, space="buy", optimize=True)
    buy_vmt_target_vol = DecimalParameter(0.10, 0.60, default=0.25, decimals=2, space="buy", optimize=True)
    buy_vmt_min_edge = DecimalParameter(0.001, 0.050, default=0.005, decimals=3, space="buy", optimize=True)
    buy_vmt_min_liq_ratio = DecimalParameter(0.25, 2.00, default=0.50, decimals=2, space="buy", optimize=True)
    buy_vmt_min_quote_volume = IntParameter(10_000, 10_000_000, default=100_000, space="buy", optimize=False)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        fast = int(self.buy_vmt_fast.value)
        slow = int(self.buy_vmt_slow.value)
        returns = close.pct_change()
        vol = returns.rolling(48, min_periods=24).std() * np.sqrt(24 * 365)
        ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
        ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
        normalized_slope = (ema_fast / ema_slow - 1.0) / vol.replace(0, np.nan)
        momentum = close.pct_change(fast) / vol.replace(0, np.nan)
        dataframe["vmt_score"] = (np.sign(normalized_slope) + np.sign(momentum)) * 0.5
        dataframe["vmt_vol"] = vol
        dataframe["vmt_scale"] = (float(self.buy_vmt_target_vol.value) / vol.replace(0, np.nan)).clip(0.20, 1.25).fillna(0.20)
        dataframe["vmt_risk_on"] = vol.le(float(self.buy_vmt_max_vol.value))
        dataframe["vmt_expected_move"] = close.pct_change(fast).abs()
        dataframe = quote_volume_features(dataframe, "vmt")
        dataframe["vmt_cost_floor"] = execution_cost_floor(self.config)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        liquid = (
            dataframe["vmt_quote_volume"].ge(float(self.buy_vmt_min_quote_volume.value))
            & dataframe["vmt_volume_ratio"].ge(float(self.buy_vmt_min_liq_ratio.value))
        )
        edge = dataframe["vmt_expected_move"].ge(
            dataframe["vmt_cost_floor"] + float(self.buy_vmt_min_edge.value)
        )
        active = dataframe["vmt_risk_on"] & liquid & edge
        long = active & dataframe["vmt_score"].ge(float(self.buy_vmt_min_score.value))
        short = active & dataframe["vmt_score"].le(-float(self.buy_vmt_min_score.value))
        dataframe["enter_long"] = long.astype(int)
        dataframe["enter_short"] = short.astype(int)
        dataframe["enter_tag"] = np.where(long, "vmt_trend_long", np.where(short, "vmt_trend_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = (~dataframe["vmt_risk_on"] | (dataframe["vmt_score"] < 0)).astype(int)
        dataframe["exit_short"] = (~dataframe["vmt_risk_on"] | (dataframe["vmt_score"] > 0)).astype(int)
        dataframe["exit_tag"] = "vmt_cash_or_flip"
        return dataframe

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        try:
            frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            scale = float(frame.iloc[-1].get("vmt_scale", 0.20)) if frame is not None and not frame.empty else 0.20
        except Exception:
            scale = 0.20
        return min(float(max_stake), max(float(min_stake or 0), float(proposed_stake) * scale))


class VolatilityManagedTrendCashSpot(VolatilityManagedTrendCash):
    """Long-only spot validation variant with the same defensive cash state."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_short"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_exit_trend(dataframe, metadata)
        dataframe["exit_short"] = 0
        return dataframe
