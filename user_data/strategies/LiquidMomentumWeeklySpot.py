"""Lower-turnover weekly liquid momentum validation lane."""

from freqtrade.strategy import DecimalParameter, IntParameter

from LiquidMomentumSpot import LiquidMomentumSpot


class LiquidMomentumWeeklySpot(LiquidMomentumSpot):
    """Seven-day lookback and weekly rebalancing defaults, kept frozen."""

    buy_lms_lookback = IntParameter(24, 168, default=42, space="buy", optimize=False, load=True)
    buy_lms_rebalance_bars = IntParameter(24, 84, default=42, space="buy", optimize=False, load=True)
    buy_lms_min_edge = DecimalParameter(0.0, 0.20, default=0.02, decimals=3, space="buy", optimize=False, load=True)
    buy_lms_volume_ratio_min = DecimalParameter(0.10, 2.0, default=1.0, decimals=2, space="buy", optimize=False, load=True)
    sell_lms_ema = IntParameter(24, 168, default=42, space="sell", optimize=False, load=True)
