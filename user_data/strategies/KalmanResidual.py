"""Relative-value lane using a causal adaptive hedge ratio."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter
from pandas import DataFrame

from RelativeValueBucket import RelativeValueBucket
from advanced_strategy_helpers import kalman_residual


class KalmanResidual(RelativeValueBucket):
    buy_kalman_delta = DecimalParameter(0.00001, 0.01, default=0.0001, decimals=5, space="buy", optimize=False, load=True)
    buy_kalman_noise = DecimalParameter(0.0001, 0.10, default=0.001, decimals=4, space="buy", optimize=False, load=True)
    buy_kalman_z_max = DecimalParameter(1.0, 5.0, default=4.0, decimals=1, space="buy", optimize=False, load=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        leader = pd.to_numeric(frame.get("rv_leader_close"), errors="coerce")
        close = pd.to_numeric(frame.get("close"), errors="coerce")
        log_close = np.log(close.replace(0, np.nan))
        log_leader = np.log(leader.replace(0, np.nan))
        residual = kalman_residual(log_close, log_leader, float(self.buy_kalman_delta.value), float(self.buy_kalman_noise.value))
        mean = residual.rolling(96, min_periods=32).mean()
        sd = residual.rolling(96, min_periods=32).std(ddof=0).replace(0, np.nan)
        frame["kalman_resid_z"] = (residual - mean) / sd
        frame["rv_signal_long"] &= (frame["kalman_resid_z"] <= 0).fillna(False)
        frame["rv_signal_short"] &= (frame["kalman_resid_z"] >= 0).fillna(False)
        frame["rv_signal_long"] &= (frame["kalman_resid_z"].abs() <= float(self.buy_kalman_z_max.value)).fillna(False)
        frame["rv_signal_short"] &= (frame["kalman_resid_z"].abs() <= float(self.buy_kalman_z_max.value)).fillna(False)
        return frame
