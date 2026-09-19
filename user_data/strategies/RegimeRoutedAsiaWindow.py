"""Controlled UTC-session research lane for RegimeRouted.

This subclass exists to test the pre-specified 00:00-07:00 UTC
Asia/overnight hypothesis. It is not the production default and should not be
interpreted as an optimized session rule.
"""

from freqtrade.strategy import BooleanParameter, IntParameter

from RegimeRouted import RegimeRouted


class RegimeRoutedAsiaWindow(RegimeRouted):
    """RegimeRouted entries restricted to the 00:00-07:00 UTC window."""

    buy_tod_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_tod_apply_aux_only = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_tod_start_hour = IntParameter(0, 23, default=0, space="buy", optimize=False, load=True)
    buy_tod_end_hour = IntParameter(1, 24, default=7, space="buy", optimize=False, load=True)
    buy_tod_utc_offset_hours = IntParameter(-12, 14, default=0, space="buy", optimize=False, load=True)
