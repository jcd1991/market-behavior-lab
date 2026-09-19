"""Previous-day volume-profile proxy using native 5-minute OHLCV only."""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IStrategy
from pandas import DataFrame


class VolumeProfileOHLCVProxy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 600
    stoploss = -0.04
    minimal_roi = {"0": 100.0}

    # This is a normalized candle-volume proxy, not literal trades-per-second.
    buy_vp_tape_speed = DecimalParameter(0.0, 0.0200, default=0.0010, decimals=4, space="buy", optimize=True)
    buy_vp_value_width = DecimalParameter(0.25, 1.50, default=0.75, decimals=2, space="buy", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        date = pd.to_datetime(dataframe["date"], utc=True)
        typical = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3.0
        volume = pd.to_numeric(dataframe["volume"], errors="coerce").fillna(0.0)
        day = date.dt.floor("D")
        weighted = typical * volume
        grouped = pd.DataFrame({"day": day, "high": dataframe["high"], "low": dataframe["low"], "weighted": weighted, "volume": volume}).groupby("day")
        daily = grouped.agg({"high": "max", "low": "min", "weighted": "sum", "volume": "sum"})
        daily["poc"] = daily["weighted"] / daily["volume"].replace(0, np.nan)
        daily["dispersion"] = grouped.apply(lambda frame: np.sqrt(np.average((typical.loc[frame.index] - daily.loc[frame.name, "poc"]) ** 2, weights=np.maximum(volume.loc[frame.index], 1e-12))))
        width = float(self.buy_vp_value_width.value)
        daily["val"] = (daily["poc"] - width * daily["dispersion"]).clip(lower=daily["low"])
        daily["vah"] = (daily["poc"] + width * daily["dispersion"]).clip(upper=daily["high"])
        daily = daily.shift(1)
        lookup = day.map(daily["poc"]).to_numpy()
        dataframe["vp_poc"] = lookup
        dataframe["vp_val"] = day.map(daily["val"]).to_numpy()
        dataframe["vp_vah"] = day.map(daily["vah"]).to_numpy()
        mean_volume = volume.rolling(12, min_periods=6).mean().replace(0, np.nan)
        dataframe["vp_tape_speed"] = ((dataframe["close"] - dataframe["open"]) / dataframe["open"].replace(0, np.nan)) * (volume / mean_volume)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        speed = float(self.buy_vp_tape_speed.value)
        dataframe["enter_long"] = (dataframe["close"].lt(dataframe["vp_val"]) & dataframe["vp_tape_speed"].ge(speed)).astype(int)
        dataframe["enter_short"] = (dataframe["close"].gt(dataframe["vp_vah"]) & dataframe["vp_tape_speed"].le(-speed)).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "volume_profile_long", np.where(dataframe["enter_short"], "volume_profile_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["close"].ge(dataframe["vp_poc"]).astype(int)
        dataframe["exit_short"] = dataframe["close"].le(dataframe["vp_poc"]).astype(int)
        dataframe["exit_tag"] = "volume_profile_poc"
        return dataframe
