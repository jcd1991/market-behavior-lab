"""Causal reconstruction of the archived 15-minute momentum basket.

The historical ``MomentumRegimeBasket15mLb30`` result imported a base module
that was not included in the public checkout.  This file restores the
documented mechanics in a reviewable form:

* previous-closed-day BTC regime: close above a 100-day SMA;
* previous-closed-day per-asset trend: close above a 50-day SMA;
* cross-sectional momentum ranking over a configurable daily lookback;
* top-three selection and hourly signal evaluation on 15-minute candles;
* a causal quote-volume cap on new stake requests.

It is intentionally marked as a reconstruction.  Results from this class are
new evidence for the reconstructed implementation, not a silent relabeling of
the archived export as an exact source replay.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy
from pandas import DataFrame

_STRATEGIES_DIR = Path(__file__).parent
if str(_STRATEGIES_DIR) not in sys.path:
    sys.path.insert(0, str(_STRATEGIES_DIR))


def _utc_dates(frame: DataFrame) -> pd.Series:
    return pd.to_datetime(frame["date"], utc=True, errors="coerce")


def _daily_close(frame: DataFrame) -> pd.Series:
    work = frame[["date", "close"]].copy()
    work["date"] = pd.to_datetime(work["date"], utc=True, errors="coerce")
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    work = work.dropna().sort_values("date").set_index("date")
    # The resampled candle is only available after the day closes.  Shifting
    # the derived features below prevents a same-day daily-close lookahead.
    return work["close"].resample("1D").last().dropna()


def _forward_fill_daily(values: pd.Series, dates: pd.Series) -> pd.Series:
    target = pd.DatetimeIndex(dates)
    if values.empty:
        return pd.Series(np.nan, index=dates.index, dtype=float)
    return values.reindex(target, method="ffill").set_axis(dates.index)


class MomentumRegimeBasket15m(IStrategy):
    """Long-only causal cross-sectional momentum basket reconstruction."""

    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = False
    process_only_new_candles = True
    # Freqtrade caps startup history at roughly five exchange candle-limit
    # batches.  The cache still derives the 100-day regime from all local
    # candles available to the data provider; this bound keeps the strategy
    # loadable in a normal 15-minute backtest.
    startup_candle_count = 4000
    stoploss = -0.20
    minimal_roi = {"0": 100.0}
    position_adjustment_enable = False

    MOM_LOOKBACK_DAYS = 90
    TREND_SMA_DAYS = 50
    REGIME_SMA_DAYS = 100
    TOP_N = 3
    EXIT_RANK_N = 15
    REBALANCE_BARS = 4
    FILL_VOLUME_CAP = 0.02

    buy_mrb_momentum_days = IntParameter(14, 120, default=90, space="buy", optimize=True, load=False)
    buy_mrb_top_n = IntParameter(1, 5, default=3, space="buy", optimize=True, load=False)
    buy_mrb_exit_rank = IntParameter(3, 30, default=15, space="sell", optimize=True, load=False)
    buy_mrb_volume_cap = DecimalParameter(0.002, 0.10, default=0.02, decimals=3, space="buy", optimize=True, load=False)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._market_pair = self._reference_pair(config)
        self._universe_cache: dict[str, DataFrame] = {}
        self._cache_signature: tuple[str, ...] | None = None

    @staticmethod
    def _reference_pair(config: dict) -> str:
        exchange = str(config.get("exchange", {}).get("name", "")).lower()
        quote = str(config.get("stake_currency", "USDT")).upper()
        if exchange == "coinbase":
            quote = "USD"
        return f"BTC/{quote}"

    def _pairs(self, metadata: dict) -> list[str]:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = []
        if not pairs:
            pairs = [str(metadata.get("pair", ""))]
        return [pair for pair in pairs if pair]

    def _pair_frame(self, pair: str) -> DataFrame | None:
        try:
            frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
        except Exception:
            return None
        if frame is None or frame.empty or not {"date", "close", "volume"}.issubset(frame.columns):
            return None
        return frame[["date", "close", "volume"]].copy()

    def _build_universe_cache(self, metadata: dict) -> None:
        pairs = self._pairs(metadata)
        signature = tuple(sorted(pairs))
        if self._cache_signature == signature and self._universe_cache:
            return
        raw = {pair: self._pair_frame(pair) for pair in pairs}
        raw = {pair: frame for pair, frame in raw.items() if frame is not None and not frame.empty}
        if not raw:
            self._universe_cache = {}
            self._cache_signature = signature
            return

        lookback = int(self.buy_mrb_momentum_days.value)
        trend_window = int(self.TREND_SMA_DAYS)
        regime_window = int(self.REGIME_SMA_DAYS)
        daily: dict[str, DataFrame] = {}
        for pair, frame in raw.items():
            close = _daily_close(frame)
            previous = close.shift(1)
            work = pd.DataFrame(index=close.index)
            work["momentum"] = previous.pct_change(lookback)
            work["trend_ok"] = previous.gt(previous.rolling(trend_window, min_periods=trend_window).mean())
            daily[pair] = work

        reference = daily.get(self._market_pair)
        if reference is None:
            reference = daily.get(next(iter(daily)))
        if reference is not None:
            reference_close = _daily_close(raw.get(self._market_pair, raw[next(iter(raw))])).shift(1)
            regime = reference_close.gt(reference_close.rolling(regime_window, min_periods=regime_window).mean())
        else:
            regime = pd.Series(dtype=bool)

        all_dates = pd.DatetimeIndex(sorted(set().union(*(set(frame.index) for frame in daily.values()))))
        momentum = pd.DataFrame({pair: frame["momentum"] for pair, frame in daily.items()}, index=all_dates).sort_index()
        ranks = momentum.rank(axis=1, ascending=False, method="min")
        cache: dict[str, DataFrame] = {}
        for pair, frame in raw.items():
            dates = _utc_dates(frame)
            pair_daily = daily[pair]
            pair_rank = ranks[pair] if pair in ranks else pd.Series(dtype=float)
            intraday = DataFrame(index=frame.index)
            intraday["mrb_momentum"] = _forward_fill_daily(pair_daily["momentum"], dates)
            intraday["mrb_rank"] = _forward_fill_daily(pair_rank, dates)
            intraday["mrb_trend_ok"] = _forward_fill_daily(pair_daily["trend_ok"].astype(float), dates).astype(bool)
            intraday["mrb_regime_ok"] = _forward_fill_daily(regime.astype(float), dates).astype(bool)
            cache[pair] = intraday
        self._universe_cache = cache
        self._cache_signature = signature

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        self._build_universe_cache(metadata)
        pair = str(metadata.get("pair", ""))
        derived = self._universe_cache.get(pair)
        if derived is None:
            derived = DataFrame(index=dataframe.index)
            derived["mrb_momentum"] = np.nan
            derived["mrb_rank"] = np.nan
            derived["mrb_trend_ok"] = False
            derived["mrb_regime_ok"] = False
        for column in derived.columns:
            dataframe[column] = derived[column].to_numpy()
        dates = _utc_dates(dataframe)
        # A 15-minute feed is evaluated once per hour (four base bars).  The
        # UTC clock calculation is independent of local timezone or daylight
        # saving; it also keeps the cadence explicit for review.
        bar_number = ((dates.dt.hour * 60 + dates.dt.minute) // 15).astype("Int64")
        dataframe["mrb_rebalance"] = bar_number.mod(self.REBALANCE_BARS).eq(0)
        dataframe["mrb_quote_volume"] = pd.to_numeric(dataframe["close"], errors="coerce").abs() * pd.to_numeric(dataframe["volume"], errors="coerce").clip(lower=0.0)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        top_n = int(self.buy_mrb_top_n.value)
        allowed = dataframe["mrb_rebalance"]
        allowed &= dataframe["mrb_regime_ok"] & dataframe["mrb_trend_ok"]
        allowed &= dataframe["mrb_rank"].le(top_n)
        dataframe["enter_long"] = allowed.fillna(False).astype(int)
        dataframe["enter_tag"] = np.where(dataframe["enter_long"], "reconstructed_momentum_regime_basket", "")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_rank = int(self.buy_mrb_exit_rank.value)
        exit_signal = dataframe["mrb_rebalance"] & (
            ~dataframe["mrb_regime_ok"]
            | ~dataframe["mrb_trend_ok"]
            | dataframe["mrb_rank"].gt(exit_rank)
        )
        dataframe["exit_long"] = exit_signal.fillna(False).astype(int)
        dataframe["exit_tag"] = np.where(dataframe["exit_long"], "momentum_rank_or_regime_exit", "")
        return dataframe

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        """Cap each requested fill using only the last completed candle volume."""
        try:
            frame, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            row = frame.iloc[-1] if frame is not None and not frame.empty else None
            quote_volume = float(row.get("mrb_quote_volume", 0.0)) if row is not None else 0.0
            cap = quote_volume * float(self.buy_mrb_volume_cap.value)
            stake = min(float(proposed_stake), cap) if cap > 0 else float(proposed_stake)
        except Exception:
            stake = float(proposed_stake)
        if stake > 0 and min_stake is not None:
            stake = max(float(min_stake), stake)
        if max_stake is not None:
            stake = min(stake, float(max_stake))
        return stake


class MomentumRegimeBasket15mLb30(MomentumRegimeBasket15m):
    """Frozen 30-day ranking reconstruction for portability testing."""

    MOM_LOOKBACK_DAYS = 30
    buy_mrb_momentum_days = IntParameter(30, 30, default=30, space="buy", optimize=False, load=False)
