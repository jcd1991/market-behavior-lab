"""Cross-sectional rotation with a correlation-cluster concentration veto."""

from __future__ import annotations

from freqtrade.strategy import DecimalParameter
from pandas import DataFrame

from CrossSectionalRotation import CrossSectionalRotation


class ClusterRotation(CrossSectionalRotation):
    buy_cluster_corr_veto = DecimalParameter(0.70, 0.99, default=0.90, decimals=2, space="buy", optimize=False, load=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_indicators(dataframe, metadata)
        returns = frame["close"].pct_change(24)
        frame["cluster_corr_proxy"] = returns.rolling(96, min_periods=48).corr(returns.shift(1))
        return frame

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        frame = super().populate_entry_trend(dataframe, metadata)
        # Per-pair proxy is intentionally conservative; full cross-pair
        # clustering remains available through research/evaluation helpers.
        frame.loc[frame["cluster_corr_proxy"] >= float(self.buy_cluster_corr_veto.value), ["enter_long", "enter_short"]] = 0
        return frame
