"""Spot-only validation lane for the regime router."""

from __future__ import annotations

from freqtrade.strategy import BooleanParameter

from RegimeRouted import RegimeRouted


class RegimeRoutedSpot(RegimeRouted):
    """Long-only, unleveraged regime-routed strategy for spot markets."""

    can_short = False
    position_adjustment_enable = False
    max_entry_position_adjustment = 0
    stoploss = -0.08
    buy_trbk_use_funding = BooleanParameter(default=False, space="buy", optimize=False, load=True)

    def informative_pairs(self):
        """Request only spot OHLCV context; never mark/index/funding candles."""
        pairs = list(self.dp.current_whitelist())
        result: list[tuple[str, str]] = [(pair, "4h") for pair in pairs]
        for pair in pairs:
            if (pair, self.timeframe) not in result:
                result.append((pair, self.timeframe))
        return result

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        """Defensive spot contract: Freqtrade should not call this in spot mode."""
        return 1.0

    def adjust_trade_position(self, *args, **kwargs):
        """Disable futures-era pyramiding and de-risk adjustments for spot."""
        return None
