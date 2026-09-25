"""Cross-sectional momentum with volatility-aware position sizing."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from research_strategy_helpers import execution_cost_floor, quote_volume_features


class RiskManagedCrossSectionalTrend(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 800
    minimal_roi = {"0": 100.0}
    stoploss = -0.20

    buy_rct_momentum_bars = IntParameter(72, 240, default=144, space="buy", optimize=True)
    buy_rct_sharpe_bars = IntParameter(336, 960, default=720, space="buy", optimize=True)
    buy_rct_long_rank = DecimalParameter(0.60, 0.95, default=0.75, decimals=2, space="buy", optimize=True)
    buy_rct_short_rank = DecimalParameter(0.05, 0.40, default=0.25, decimals=2, space="buy", optimize=True)
    buy_rct_target_vol = DecimalParameter(0.10, 0.60, default=0.25, decimals=2, space="buy", optimize=True)
    buy_rct_min_edge = DecimalParameter(0.001, 0.050, default=0.005, decimals=3, space="buy", optimize=True)
    buy_rct_min_liq_ratio = DecimalParameter(0.25, 2.00, default=0.50, decimals=2, space="buy", optimize=True)
    buy_rct_min_quote_volume = IntParameter(10_000, 10_000_000, default=100_000, space="buy", optimize=False)

    def _universe(self, metric: str) -> pd.DataFrame:
        values = {}
        pairs = list(self.dp.current_whitelist() or []) if self.dp else []
        for pair in pairs:
            try:
                frame = self.dp.get_pair_dataframe(pair, self.timeframe)
            except Exception:
                continue
            if frame is None or frame.empty:
                continue
            dates = pd.to_datetime(frame["date"], utc=True)
            close = pd.to_numeric(frame["close"], errors="coerce")
            returns = close.pct_change()
            if metric == "momentum":
                values[pair] = pd.Series(close.pct_change(int(self.buy_rct_momentum_bars.value)).to_numpy(), index=dates)
            else:
                bars = int(self.buy_rct_sharpe_bars.value)
                values[pair] = pd.Series((returns.rolling(bars, min_periods=bars // 2).mean() / returns.rolling(bars, min_periods=bars // 2).std()).to_numpy(), index=dates)
        return pd.DataFrame(values).sort_index()

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        close = pd.to_numeric(dataframe["close"], errors="coerce")
        dates = pd.to_datetime(dataframe["date"], utc=True)
        momentum = close.pct_change(int(self.buy_rct_momentum_bars.value))
        returns = close.pct_change()
        sharpe_bars = int(self.buy_rct_sharpe_bars.value)
        sharpe = returns.rolling(sharpe_bars, min_periods=sharpe_bars // 2).mean() / returns.rolling(sharpe_bars, min_periods=sharpe_bars // 2).std()
        vol = returns.rolling(48, min_periods=24).std() * np.sqrt(24 * 365)
        universe_momentum = self._universe("momentum")
        universe_sharpe = self._universe("sharpe")
        if metadata["pair"] in universe_momentum:
            dataframe["rct_momentum_rank"] = universe_momentum.rank(axis=1, pct=True)[metadata["pair"]].reindex(dates, method="ffill").to_numpy()
        else:
            dataframe["rct_momentum_rank"] = np.nan
        if metadata["pair"] in universe_sharpe:
            dataframe["rct_sharpe_rank"] = universe_sharpe.rank(axis=1, pct=True)[metadata["pair"]].reindex(dates, method="ffill").to_numpy()
        else:
            dataframe["rct_sharpe_rank"] = np.nan
        dataframe["rct_momentum"] = momentum
        dataframe["rct_sharpe"] = sharpe
        dataframe["rct_vol"] = vol
        dataframe["rct_scale"] = (float(self.buy_rct_target_vol.value) / vol.replace(0, np.nan)).clip(0.20, 1.25).fillna(0.20)
        dataframe = quote_volume_features(dataframe, "rct")
        dataframe["rct_cost_floor"] = execution_cost_floor(self.config)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        liquid = (
            dataframe["rct_quote_volume"].ge(float(self.buy_rct_min_quote_volume.value))
            & dataframe["rct_volume_ratio"].ge(float(self.buy_rct_min_liq_ratio.value))
        )
        edge = dataframe["rct_momentum"].abs().ge(
            dataframe["rct_cost_floor"] + float(self.buy_rct_min_edge.value)
        )
        long = (dataframe["rct_momentum_rank"] >= float(self.buy_rct_long_rank.value)) & (dataframe["rct_sharpe"] > 0) & liquid & edge
        short = (dataframe["rct_momentum_rank"] <= float(self.buy_rct_short_rank.value)) & (dataframe["rct_sharpe"] < 0) & liquid & edge
        dataframe["enter_long"] = long.astype(int)
        dataframe["enter_short"] = short.astype(int)
        dataframe["enter_tag"] = np.where(long, "rct_top_rank", np.where(short, "rct_bottom_rank", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = ((dataframe["rct_momentum_rank"] < 0.50) | (dataframe["rct_sharpe"] <= 0)).astype(int)
        dataframe["exit_short"] = ((dataframe["rct_momentum_rank"] > 0.50) | (dataframe["rct_sharpe"] >= 0)).astype(int)
        dataframe["exit_tag"] = "rct_rank_reversal"
        return dataframe

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        try:
            frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            scale = float(frame.iloc[-1].get("rct_scale", 0.20)) if frame is not None and not frame.empty else 0.20
        except Exception:
            scale = 0.20
        return min(float(max_stake), max(float(min_stake or 0), float(proposed_stake) * scale))


class RiskManagedCrossSectionalTrendSpot(RiskManagedCrossSectionalTrend):
    """Long-only spot validation variant; short ranking is not silently used."""

    can_short = False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe["enter_short"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_exit_trend(dataframe, metadata)
        dataframe["exit_short"] = 0
        return dataframe
