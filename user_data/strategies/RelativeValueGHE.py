"""Experimental residual mean-reversion lane with a causal GHE filter."""

from __future__ import annotations

from freqtrade.strategy import BooleanParameter, CategoricalParameter, DecimalParameter, IntParameter
from pandas import DataFrame

from RelativeValueBucket import RelativeValueBucket
from ghe import rolling_generalized_hurst


class RelativeValueGHE(RelativeValueBucket):
    """Fixed leader-map residual strategy filtered for anti-persistence.

    This is deliberately not a rolling pair optimizer.  The existing leader
    map remains fixed so the experiment tests the GHE selector rather than
    silently introducing pair-selection lookahead.
    """

    buy_rv_ghe_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_rv_ghe_window = IntParameter(48, 240, default=96, space="buy", optimize=False, load=True)
    buy_rv_ghe_max = DecimalParameter(0.25, 0.75, default=0.48, decimals=2, space="buy", optimize=False, load=True)
    buy_rv_ghe_q = CategoricalParameter(["0.5", "1.0", "2.0"], default="1.0", space="buy", optimize=False, load=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        frame["rv_ghe"] = float("nan")
        if not bool(self.buy_rv_ghe_enabled.value):
            return frame
        residual = frame.get("rv_resid")
        if residual is None:
            frame["rv_signal_long"] = False
            frame["rv_signal_short"] = False
            return frame
        ghe = rolling_generalized_hurst(
            residual,
            window=int(self.buy_rv_ghe_window.value),
            q=float(self.buy_rv_ghe_q.value),
        )
        frame["rv_ghe"] = ghe
        allowed = (ghe <= float(self.buy_rv_ghe_max.value)).fillna(False)
        frame["rv_signal_long"] = frame["rv_signal_long"].fillna(False).astype(bool) & allowed
        frame["rv_signal_short"] = frame["rv_signal_short"].fillna(False).astype(bool) & allowed
        return frame
