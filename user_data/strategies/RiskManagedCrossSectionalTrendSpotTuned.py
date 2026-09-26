"""Research-only frozen candidate from the bounded 2024 parameter screen.

This class is kept separate from the baseline parameter file so a tuning
result cannot silently replace the reproducible control lane.  It is not a
claim that the training-window selection generalizes.
"""

from freqtrade.strategy import DecimalParameter, IntParameter

from RiskManagedCrossSectionalTrend import RiskManagedCrossSectionalTrendSpot


class RiskManagedCrossSectionalTrendSpotTuned(RiskManagedCrossSectionalTrendSpot):
    """2024-only tuned candidate, to be judged on locked later windows."""

    buy_rct_momentum_bars = IntParameter(72, 240, default=95, space="buy", optimize=False, load=False)
    buy_rct_sharpe_bars = IntParameter(336, 960, default=837, space="buy", optimize=False, load=False)
    buy_rct_long_rank = DecimalParameter(0.60, 0.95, default=0.63, decimals=2, space="buy", optimize=False, load=False)
    buy_rct_short_rank = DecimalParameter(0.05, 0.40, default=0.14, decimals=2, space="buy", optimize=False, load=False)
    buy_rct_target_vol = DecimalParameter(0.10, 0.60, default=0.52, decimals=2, space="buy", optimize=False, load=False)
    buy_rct_min_edge = DecimalParameter(0.001, 0.050, default=0.010, decimals=3, space="buy", optimize=False, load=False)
    buy_rct_min_liq_ratio = DecimalParameter(0.25, 2.00, default=1.20, decimals=2, space="buy", optimize=False, load=False)

    def load_params_from_file(self) -> dict:
        """Do not inherit the baseline JSON when screening this candidate."""

        return {}
