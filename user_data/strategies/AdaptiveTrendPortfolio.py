"""Six-hour decision trend lane with rolling Sharpe and ATR trailing exits."""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

try:
    from user_data.strategies.research_strategy_helpers import scheduled_bars, utc_series
except ModuleNotFoundError:
    from research_strategy_helpers import scheduled_bars, utc_series


class AdaptiveTrendPortfolio(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 260
    stoploss = -0.20
    minimal_roi = {"0": 100.0}

    buy_atp_momentum_bars = IntParameter(48, 240, default=120, space="buy", optimize=True)
    buy_atp_sharpe_bars = IntParameter(120, 720, default=360, space="buy", optimize=True)
    buy_atp_entry_edge = DecimalParameter(0.01, 0.30, default=0.04, decimals=3, space="buy", optimize=True)
    buy_atp_atr_multiplier = DecimalParameter(1.5, 5.0, default=2.5, decimals=2, space="sell", optimize=True)
    buy_atp_rebalance_hours = IntParameter(4, 12, default=6, space="buy", optimize=True)

    def _universe_median(self, dataframe: DataFrame, column: str) -> pd.Series:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        lookback = int(self.buy_atp_momentum_bars.value)
        values = []
        for pair in pairs:
            try:
                frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
            except Exception:
                frame = None
            if frame is None or frame.empty:
                continue
            idx = utc_series(frame["date"])
            px = pd.to_numeric(frame["close"], errors="coerce")
            ret = px.pct_change(lookback)
            roll_ret = px.pct_change().rolling(int(self.buy_atp_sharpe_bars.value), min_periods=lookback).mean()
            roll_vol = px.pct_change().rolling(int(self.buy_atp_sharpe_bars.value), min_periods=lookback).std().replace(0, np.nan)
            series = ret if column == "momentum" else roll_ret / roll_vol
            values.append(pd.Series(series.to_numpy(), index=idx))
        if not values:
            return pd.Series(np.nan, index=dataframe.index)
        target = pd.DatetimeIndex(utc_series(dataframe["date"]).to_numpy())
        return pd.concat(values, axis=1).median(axis=1).sort_index().reindex(target, method="ffill").set_axis(dataframe.index)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        ret = close.pct_change(int(self.buy_atp_momentum_bars.value))
        rolling_return = close.pct_change().rolling(int(self.buy_atp_sharpe_bars.value), min_periods=120).mean()
        rolling_vol = close.pct_change().rolling(int(self.buy_atp_sharpe_bars.value), min_periods=120).std().replace(0, np.nan)
        dataframe["atp_momentum"] = ret
        dataframe["atp_sharpe"] = rolling_return / rolling_vol
        dataframe["atp_momentum_edge"] = ret - self._universe_median(dataframe, "momentum")
        dataframe["atp_sharpe_edge"] = dataframe["atp_sharpe"] - self._universe_median(dataframe, "sharpe")
        dataframe["atp_atr"] = ta.ATR(dataframe, timeperiod=24)
        dataframe["atp_schedule"] = scheduled_bars(dataframe, int(self.buy_atp_rebalance_hours.value))
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        edge = float(self.buy_atp_entry_edge.value)
        active = dataframe["atp_schedule"] & dataframe["atp_sharpe_edge"].gt(0)
        dataframe["enter_long"] = (active & dataframe["atp_momentum_edge"].ge(edge)).astype(int)
        dataframe["enter_short"] = (active & dataframe["atp_momentum_edge"].le(-edge)).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "adaptive_trend_long", np.where(dataframe["enter_short"], "adaptive_trend_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["atp_momentum_edge"].le(0).astype(int)
        dataframe["exit_short"] = dataframe["atp_momentum_edge"].ge(0).astype(int)
        dataframe["exit_tag"] = "adaptive_momentum_exit"
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time, current_rate: float, current_profit: float, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None
        atr = float(dataframe.iloc[-1].get("atp_atr", np.nan))
        if not np.isfinite(atr) or trade.max_rate is None:
            return None
        stop = float(trade.max_rate) - float(self.buy_atp_atr_multiplier.value) * atr
        if current_rate < stop:
            return "adaptive_atr_trailing"
        return None
