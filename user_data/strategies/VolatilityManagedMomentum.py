"""Slow residual/momentum lane with volatility-managed sizing."""

from __future__ import annotations

from freqtrade.strategy import DecimalParameter, IntParameter
from pandas import DataFrame

from SlowResidualRotation import SlowResidualRotation
from advanced_strategy_helpers import volatility_target_scale


class VolatilityManagedMomentum(SlowResidualRotation):
    buy_vmm_vol_window = IntParameter(6, 48, default=12, space="buy", optimize=False, load=True)
    buy_vmm_target_vol = DecimalParameter(0.05, 0.80, default=0.25, decimals=2, space="buy", optimize=False, load=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        frame["vmm_scale"] = volatility_target_scale(frame["close"], int(self.buy_vmm_vol_window.value), float(self.buy_vmm_target_vol.value), 0.25, 1.50)
        return frame

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        base = super().custom_stake_amount(pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs)
        try:
            frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            scale = float(frame.iloc[-1].get("vmm_scale", 1.0)) if frame is not None and not frame.empty else 1.0
        except Exception:
            scale = 1.0
        return min(float(max_stake), max(0.0, float(base) * scale))
