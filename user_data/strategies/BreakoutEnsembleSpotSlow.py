"""Predeclared slower breakout-ensemble candidate used for forward testing."""

from freqtrade.strategy import IntParameter

from BreakoutEnsembleSpot import BreakoutEnsembleSpot


class BreakoutEnsembleSpotSlow(BreakoutEnsembleSpot):
    """The only slower-horizon candidate selected by the training grid.

    This class is kept separate so its parameters are visible and frozen when
    it is run on the forward window.  It is not a claim that the grid winner
    is portable; the forward report decides that.
    """

    HORIZONS = (18, 36, 72, 144)
    buy_bes_votes = IntParameter(1, 4, default=2, space="buy", optimize=False, load=True)
