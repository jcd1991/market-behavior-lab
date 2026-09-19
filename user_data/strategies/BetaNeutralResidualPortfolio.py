"""Signal-level BTC-beta-capped residual lane.

This computes a rolling residual and applies a beta cap per pair. It is not a full
portfolio hedge; Freqtrade's pair strategy interface cannot guarantee that all
open positions sum to zero beta without an external allocator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter
from pandas import DataFrame

from RelativeValueStatArb import RelativeValueStatArb
from research_strategy_helpers import scheduled_bars


class BetaNeutralResidualPortfolio(RelativeValueStatArb):
    buy_bnrp_entry_z = DecimalParameter(1.0, 3.5, default=1.75, decimals=2, space="buy", optimize=True)
    buy_bnrp_beta_abs_max = DecimalParameter(0.25, 1.50, default=1.25, decimals=2, space="buy", optimize=True)
    buy_bnrp_schedule_hours = IntParameter(4, 48, default=24, space="buy", optimize=True)
    buy_bnrp_residual_window = IntParameter(48, 240, default=96, space="buy", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        frame["bnrp_beta"] = frame.get("rva_beta", np.nan)
        frame["bnrp_schedule"] = scheduled_bars(frame, int(self.buy_bnrp_schedule_hours.value))
        # RelativeValueStatArb computes the causal residual z-score and beta;
        # retain only scheduled entries inside both explicit risk limits.
        beta_ok = frame["bnrp_beta"].abs().le(float(self.buy_bnrp_beta_abs_max.value))
        z_ok = frame["rva_z"].abs().ge(float(self.buy_bnrp_entry_z.value))
        allowed = frame["bnrp_schedule"] & beta_ok & z_ok
        enter_long = frame["enter_long"] if "enter_long" in frame else pd.Series(0, index=frame.index)
        enter_short = frame["enter_short"] if "enter_short" in frame else pd.Series(0, index=frame.index)
        frame["enter_long"] = (enter_long.astype(bool) & allowed).astype(int)
        frame["enter_short"] = (enter_short.astype(bool) & allowed).astype(int)
        return frame
