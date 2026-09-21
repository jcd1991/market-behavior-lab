"""Independent rolling residual mean-reversion research strategy.

This is an original implementation for Market Behavior Lab.  It uses only
Freqtrade OHLCV data and a configured reference pair; it does not import or
copy the external GPL strategies evaluated in the research log.
"""

import numpy as np
import pandas as pd
from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter


class CointegrationResidual(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    startup_candle_count = 300
    process_only_new_candles = True
    can_short = False
    minimal_roi = {"0": 0.03, "240": 0.015, "720": 0}
    stoploss = -0.08
    trailing_stop = False

    formation_window = IntParameter(120, 360, default=240, space="buy")
    entry_z = DecimalParameter(1.2, 3.0, default=1.8, decimals=1, space="buy")
    exit_z = DecimalParameter(0.0, 1.0, default=0.4, decimals=1, space="sell")
    min_corr = DecimalParameter(0.50, 0.99, default=0.75, decimals=2, space="buy")

    @staticmethod
    def _reference_pair(config: dict, pair: str) -> str:
        configured = config.get("cointegration_reference_pair")
        if configured and configured != pair:
            return configured
        quote = pair.split("/")[-1].split(":")[0]
        return f"BTC/{quote}"

    def informative_pairs(self):
        pairs = self.dp.current_whitelist() if self.dp else []
        return [(self._reference_pair(self.config, pair), self.timeframe) for pair in pairs]

    @staticmethod
    def _rolling_residual(frame: DataFrame, ref: DataFrame, window: int) -> DataFrame:
        left = frame[["date", "close"]].rename(columns={"close": "asset_close"})
        right = ref[["date", "close"]].rename(columns={"close": "reference_close"})
        merged = pd.merge_asof(left.sort_values("date"), right.sort_values("date"), on="date")
        y = np.log(merged["asset_close"].replace(0, np.nan))
        x = np.log(merged["reference_close"].replace(0, np.nan))
        cov = y.rolling(window).cov(x)
        var = x.rolling(window).var().replace(0, np.nan)
        beta = (cov / var).clip(-5, 5)
        residual = y - beta * x
        mean = residual.rolling(window).mean()
        std = residual.rolling(window).std().replace(0, np.nan)
        merged["cointegration_beta"] = beta.to_numpy()
        merged["cointegration_residual"] = residual.to_numpy()
        merged["cointegration_z"] = ((residual - mean) / std).to_numpy()
        merged["cointegration_corr"] = y.rolling(window).corr(x).to_numpy()
        return merged[["date", "cointegration_beta", "cointegration_residual", "cointegration_z", "cointegration_corr"]]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ref_pair = self._reference_pair(self.config, metadata["pair"])
        if self.dp and ref_pair != metadata["pair"]:
            ref = self.dp.get_pair_dataframe(pair=ref_pair, timeframe=self.timeframe)
            if not ref.empty:
                residual = self._rolling_residual(dataframe, ref, self.formation_window.value)
                dataframe = pd.merge_asof(dataframe.sort_values("date"), residual.sort_values("date"), on="date")
        for col, default in (("cointegration_beta", np.nan), ("cointegration_residual", np.nan),
                             ("cointegration_z", np.nan), ("cointegration_corr", np.nan)):
            if col not in dataframe:
                dataframe[col] = default
        dataframe["atr_pct"] = ta.ATR(dataframe, timeperiod=14) / dataframe["close"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["cointegration_z"] < -self.entry_z.value)
            & (dataframe["cointegration_corr"] >= self.min_corr.value)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        dataframe.loc[dataframe["cointegration_z"] < -self.entry_z.value, "enter_tag"] = "residual_discount"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["cointegration_z"] >= -self.exit_z.value,
            "exit_long",
        ] = 1
        return dataframe
