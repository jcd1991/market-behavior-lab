"""Regime router with causal volatility-targeted position sizing."""

from __future__ import annotations

from freqtrade.strategy import DecimalParameter, IntParameter
from pandas import DataFrame

from RegimeRouted import RegimeRouted
from advanced_strategy_helpers import volatility_target_scale


class RegimeRoutedVolTarget(RegimeRouted):
    buy_avt_vol_window = IntParameter(12, 96, default=24, space="buy", optimize=False, load=True)
    buy_avt_target_vol = DecimalParameter(0.05, 0.80, default=0.25, decimals=2, space="buy", optimize=False, load=True)
    buy_avt_scale_floor = DecimalParameter(0.10, 1.00, default=0.25, decimals=2, space="buy", optimize=False, load=True)
    buy_avt_scale_ceiling = DecimalParameter(1.00, 2.00, default=1.50, decimals=2, space="buy", optimize=False, load=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        frame["avt_scale"] = volatility_target_scale(
            frame["close"], int(self.buy_avt_vol_window.value), float(self.buy_avt_target_vol.value),
            float(self.buy_avt_scale_floor.value), float(self.buy_avt_scale_ceiling.value),
        )
        return frame

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        base = super().custom_stake_amount(pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs)
        try:
            frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            scale = float(frame.iloc[-1].get("avt_scale", 1.0)) if frame is not None and not frame.empty else 1.0
        except Exception:
            scale = 1.0
        return min(float(max_stake), max(0.0, float(base) * scale))
