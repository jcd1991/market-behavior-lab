"""Strict historical-funding validation lane for perpetual RegimeRouted."""

from freqtrade.strategy import BooleanParameter

from RegimeRouted import RegimeRouted


class RegimeRoutedFundingFilter(RegimeRouted):
    """Baseline router with a required, side-aware historical funding gate."""

    buy_deriv_dq_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_deriv_dq_apply_aux_only = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_deriv_dq_use_funding = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_deriv_dq_use_oi = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_deriv_dq_use_basis = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_deriv_dq_allow_missing = BooleanParameter(default=False, space="buy", optimize=False, load=True)
