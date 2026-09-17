from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import (
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    IStrategy,
    stoploss_from_open,
)
from pandas import DataFrame


logger = logging.getLogger(__name__)


_MEME_PAIRS = {
    "PEPE/USD:USD",
    "BONK/USD:USD",
}

_TAIL_PAIRS = {
    "PEPE/USD:USD",
    "BONK/USD:USD",
    "SEI/USD:USD",
    "WLD/USD:USD",
}

_MAJORS_PAIRS = {
    "ETH/USD:USD",
    "DOGE/USD:USD",
    "ADA/USD:USD",
    "LINK/USD:USD",
    "DOT/USD:USD",
    "NEAR/USD:USD",
    "UNI/USD:USD",
    "ATOM/USD:USD",
    "FIL/USD:USD",
    "LTC/USD:USD",
    "ARB/USD:USD",
    "OP/USD:USD",
    "TRX/USD:USD",
    "ETC/USD:USD",
    "AAVE/USD:USD",
    "INJ/USD:USD",
    "TIA/USD:USD",
    "FET/USD:USD",
    "RNDR/USD:USD",
    "JUP/USD:USD",
}


class CrossSectionalRotation_KR(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 400
    position_adjustment_enable = False
    use_custom_stoploss = True
    stoploss = -0.15
    minimal_roi = {"0": 100.0}

    order_types = {
        "entry": "market",
        "exit": "market",
        "emergency_exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
        "stoploss_on_exchange_interval": 60,
        "stoploss_on_exchange_market_ratio": 0.99,
    }

    buy_xsr_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_xsr_universe_profile = CategoricalParameter(
        ["full", "alts", "liquid_alts", "majors"],
        default="liquid_alts",
        space="buy",
        optimize=False,
        load=True,
    )
    buy_xsr_momo_lookback = IntParameter(6, 96, default=24, space="buy", optimize=False, load=True)
    buy_xsr_reversal_lookback = IntParameter(2, 48, default=6, space="buy", optimize=False, load=True)
    buy_xsr_dispersion_lookback = IntParameter(6, 96, default=24, space="buy", optimize=False, load=True)
    buy_xsr_relvol_len = IntParameter(8, 72, default=24, space="buy", optimize=False, load=True)
    buy_xsr_relvol_min = DecimalParameter(0.60, 2.00, default=0.90, decimals=2, space="buy", optimize=True, load=True)
    buy_xsr_atr_pct_max = DecimalParameter(0.01, 0.20, default=0.08, decimals=3, space="buy", optimize=True, load=True)
    buy_xsr_require_ema_bias = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_xsr_rebalance_hours = IntParameter(1, 12, default=4, space="buy", optimize=False, load=True)
    buy_xsr_signal_cooldown_bars = IntParameter(1, 24, default=6, space="buy", optimize=False, load=True)
    buy_xsr_ema_fast = IntParameter(12, 96, default=48, space="buy", optimize=False, load=True)
    buy_xsr_ema_slow = IntParameter(24, 200, default=144, space="buy", optimize=False, load=True)
    buy_xsr_long_topn = IntParameter(1, 6, default=2, space="buy", optimize=True, load=True)
    buy_xsr_short_topn = IntParameter(1, 6, default=2, space="buy", optimize=True, load=True)
    buy_xsr_long_min_score = DecimalParameter(0.05, 0.80, default=0.18, decimals=2, space="buy", optimize=True, load=True)
    buy_xsr_short_min_score = DecimalParameter(0.05, 0.80, default=0.18, decimals=2, space="buy", optimize=True, load=True)
    buy_xsr_max_open_longs = IntParameter(1, 6, default=2, space="buy", optimize=False, load=True)
    buy_xsr_max_open_shorts = IntParameter(1, 6, default=2, space="buy", optimize=False, load=True)
    buy_xsr_w_momo = DecimalParameter(0.0, 1.0, default=0.45, decimals=2, space="buy", optimize=True, load=True)
    buy_xsr_w_reversal = DecimalParameter(0.0, 1.0, default=0.15, decimals=2, space="buy", optimize=True, load=True)
    buy_xsr_w_basis = DecimalParameter(0.0, 1.0, default=0.20, decimals=2, space="buy", optimize=True, load=True)
    buy_xsr_w_funding = DecimalParameter(0.0, 1.0, default=0.10, decimals=2, space="buy", optimize=True, load=True)
    buy_xsr_w_dispersion = DecimalParameter(0.0, 1.0, default=0.10, decimals=2, space="buy", optimize=True, load=True)
    buy_xsr_gross_cap_pct = DecimalParameter(0.05, 0.60, default=0.32, decimals=2, space="buy", optimize=False, load=True)
    buy_xsr_stake_floor_mult = DecimalParameter(0.50, 1.00, default=0.80, decimals=2, space="buy", optimize=False, load=True)
    buy_xsr_stake_ceiling_mult = DecimalParameter(1.00, 1.50, default=1.20, decimals=2, space="buy", optimize=False, load=True)
    buy_xsr_leverage = DecimalParameter(1.0, 3.0, default=1.0, decimals=1, space="buy", optimize=False, load=True)
    buy_xsr_debug = BooleanParameter(default=False, space="buy", optimize=False, load=True)

    sell_xsr_stoploss = DecimalParameter(-0.08, -0.005, default=-0.028, decimals=3, space="sell", optimize=True, load=True)
    sell_xsr_profit_target = DecimalParameter(0.004, 0.05, default=0.018, decimals=3, space="sell", optimize=True, load=True)
    sell_xsr_time_stop_minutes = IntParameter(60, 1440, default=480, space="sell", optimize=True, load=True)
    sell_xsr_rank_exit = IntParameter(2, 12, default=5, space="sell", optimize=True, load=True)
    sell_xsr_score_exit = DecimalParameter(-0.20, 0.30, default=0.02, decimals=2, space="sell", optimize=True, load=True)
    sell_xsr_scratch_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_xsr_scratch_arm = DecimalParameter(0.002, 0.03, default=0.008, decimals=3, space="sell", optimize=True, load=True)
    sell_xsr_scratch_stop = DecimalParameter(-0.005, 0.01, default=0.000, decimals=3, space="sell", optimize=True, load=True)
    sell_xsr_trail_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_xsr_trail_arm = DecimalParameter(0.004, 0.05, default=0.014, decimals=3, space="sell", optimize=True, load=True)
    sell_xsr_trail_offset = DecimalParameter(0.001, 0.03, default=0.006, decimals=3, space="sell", optimize=True, load=True)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._xsr_pair_cache: dict[str, pd.DataFrame] = {}
        self._xsr_cache_signature: tuple[Any, ...] | None = None
        self._xsr_hwm: dict[str, float] = {}

    def informative_pairs(self):
        if not bool(self.buy_xsr_enabled.value):
            return []
        result: list[tuple[str, str] | tuple[str, str, str]] = []
        for pair in self._xsr_pairs():
            result.append((pair, self.timeframe, "funding_rate"))
            result.append((pair, self.timeframe, "mark"))
            result.append((pair, self.timeframe, "index"))
        return result

    def _xsr_pairs(self) -> list[str]:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = list(self.config.get("exchange", {}).get("pair_whitelist", []))
        profile = str(self.buy_xsr_universe_profile.value or "liquid_alts")
        out: list[str] = []
        for pair in pairs:
            if profile in {"alts", "liquid_alts", "majors"} and pair == "BTC/USD:USD":
                continue
            if profile == "liquid_alts" and pair in _TAIL_PAIRS:
                continue
            if profile == "majors" and pair not in _MAJORS_PAIRS:
                continue
            out.append(pair)
        return out

    def _xsr_signature(self) -> tuple[Any, ...]:
        return (
            tuple(sorted(self._xsr_pairs())),
            int(self.buy_xsr_momo_lookback.value),
            int(self.buy_xsr_reversal_lookback.value),
            int(self.buy_xsr_dispersion_lookback.value),
            int(self.buy_xsr_relvol_len.value),
            int(self.buy_xsr_ema_fast.value),
            int(self.buy_xsr_ema_slow.value),
            int(self.buy_xsr_rebalance_hours.value),
            int(self.buy_xsr_signal_cooldown_bars.value),
            float(self.buy_xsr_relvol_min.value),
            float(self.buy_xsr_atr_pct_max.value),
            float(self.buy_xsr_w_momo.value),
            float(self.buy_xsr_w_reversal.value),
            float(self.buy_xsr_w_basis.value),
            float(self.buy_xsr_w_funding.value),
            float(self.buy_xsr_w_dispersion.value),
            int(self.buy_xsr_long_topn.value),
            int(self.buy_xsr_short_topn.value),
            float(self.buy_xsr_long_min_score.value),
            float(self.buy_xsr_short_min_score.value),
            bool(self.buy_xsr_require_ema_bias.value),
        )

    def _default_frame(self, dataframe: DataFrame) -> DataFrame:
        defaults = {
            "xsr_score": np.nan,
            "xsr_momo_rank": np.nan,
            "xsr_reversal_rank": np.nan,
            "xsr_basis_rank": np.nan,
            "xsr_funding_rank": np.nan,
            "xsr_dispersion_rank": np.nan,
            "xsr_long_rank": np.nan,
            "xsr_short_rank": np.nan,
            "xsr_relvol": np.nan,
            "xsr_atr_pct": np.nan,
            "xsr_long_selected": False,
            "xsr_short_selected": False,
        }
        for col, default in defaults.items():
            dataframe[col] = default
        return dataframe

    def _safe_get_open_trades(self) -> list[Any]:
        try:
            return Trade.get_open_trades()
        except Exception:
            return []

    def _wallet_total(self) -> float:
        try:
            wallet_total = float(self.wallets.get_total(self.config.get("stake_currency", "USD")))
            if wallet_total > 0:
                return wallet_total
        except Exception:
            pass
        try:
            return float(self.config.get("dry_run_wallet", 1000))
        except Exception:
            return 1000.0

    def _xsr_trade_key(self, trade: Trade) -> str:
        return f"{getattr(trade, 'id', 'na')}|{getattr(trade, 'pair', '')}|{getattr(trade, 'open_date_utc', '')}"

    def _price_frame(self, pair: str) -> pd.DataFrame | None:
        try:
            df = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
        except Exception:
            return None
        if df is None or df.empty:
            return None
        work = df.copy()
        work["__date"] = pd.to_datetime(work["date"], utc=True, errors="coerce")
        work = work.dropna(subset=["__date"]).sort_values("__date")
        if work.empty:
            return None
        return work

    @staticmethod
    def _merge_asof_numeric_series(
        base_df: pd.DataFrame | None,
        src_df: pd.DataFrame | None,
        value_col: str,
    ) -> pd.Series:
        if base_df is None or base_df.empty:
            return pd.Series(dtype=float)
        out = pd.Series(np.nan, index=base_df.index, dtype=float)
        if (
            src_df is None
            or src_df.empty
            or "__date" not in base_df.columns
            or "__date" not in src_df.columns
            or value_col not in src_df.columns
        ):
            return out
        left = base_df[["__date"]].copy().dropna(subset=["__date"]).sort_values("__date")
        if left.empty:
            return out
        right = src_df[["__date", value_col]].copy().dropna(subset=["__date"]).sort_values("__date")
        if right.empty:
            return out
        merged = pd.merge_asof(left, right, on="__date", direction="backward")
        out.loc[left.index] = pd.to_numeric(merged[value_col], errors="coerce").values
        return out

    def _funding_series(self, base_df: pd.DataFrame, pair: str) -> pd.Series:
        try:
            fr_df = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe, candle_type="funding_rate")
        except Exception:
            return pd.Series(np.nan, index=base_df.index, dtype=float)
        if fr_df is None or fr_df.empty:
            return pd.Series(np.nan, index=base_df.index, dtype=float)
        work = fr_df.copy()
        work["__date"] = pd.to_datetime(work["date"], utc=True, errors="coerce")
        funding = pd.to_numeric(work.get("funding_rate"), errors="coerce")
        if not isinstance(funding, pd.Series):
            funding = pd.Series(np.nan, index=work.index, dtype=float)
        if funding.notna().sum() == 0:
            funding = pd.to_numeric(work.get("close"), errors="coerce")
            if not isinstance(funding, pd.Series):
                funding = pd.Series(np.nan, index=work.index, dtype=float)
        if funding.notna().sum() == 0:
            funding = pd.to_numeric(work.get("open"), errors="coerce")
            if not isinstance(funding, pd.Series):
                funding = pd.Series(np.nan, index=work.index, dtype=float)
        work["__funding"] = funding
        return self._merge_asof_numeric_series(base_df, work, "__funding")

    def _basis_series(self, base_df: pd.DataFrame, pair: str) -> pd.Series:
        mark_df = None
        index_df = None
        try:
            mark_df = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe, candle_type="mark")
        except Exception:
            mark_df = None
        try:
            index_df = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe, candle_type="index")
        except Exception:
            index_df = None

        close = pd.to_numeric(base_df.get("close"), errors="coerce")
        out = pd.Series(np.nan, index=base_df.index, dtype=float)

        mark = pd.Series(np.nan, index=base_df.index, dtype=float)
        if mark_df is not None and not mark_df.empty:
            work = mark_df.copy()
            work["__date"] = pd.to_datetime(work["date"], utc=True, errors="coerce")
            mark_close = pd.to_numeric(work.get("close"), errors="coerce")
            if not isinstance(mark_close, pd.Series):
                mark_close = pd.Series(np.nan, index=work.index, dtype=float)
            work["__mark_close"] = mark_close
            mark = self._merge_asof_numeric_series(base_df, work, "__mark_close")

        index = pd.Series(np.nan, index=base_df.index, dtype=float)
        if index_df is not None and not index_df.empty:
            work = index_df.copy()
            work["__date"] = pd.to_datetime(work["date"], utc=True, errors="coerce")
            index_close = pd.to_numeric(work.get("close"), errors="coerce")
            if not isinstance(index_close, pd.Series):
                index_close = pd.Series(np.nan, index=work.index, dtype=float)
            work["__index_close"] = index_close
            index = self._merge_asof_numeric_series(base_df, work, "__index_close")

        if mark.notna().any() and index.notna().any():
            out = ((mark - index) / index.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
        elif close.notna().any() and index.notna().any():
            out = ((close - index) / index.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
        elif close.notna().any() and mark.notna().any():
            out = ((close - mark) / mark.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
        return out

    @staticmethod
    def _centered_rank_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()
        ranked = frame.rank(axis=1, pct=True, method="average")
        return ((ranked - 0.5) * 2.0).clip(lower=-1.0, upper=1.0)

    def _build_score_cache(self) -> None:
        if not bool(self.buy_xsr_enabled.value):
            self._xsr_pair_cache = {}
            self._xsr_cache_signature = self._xsr_signature()
            return

        signature = self._xsr_signature()
        if self._xsr_cache_signature == signature and self._xsr_pair_cache:
            return

        pairs = self._xsr_pairs()
        if len(pairs) < 4:
            self._xsr_pair_cache = {}
            self._xsr_cache_signature = signature
            return

        btc_df = self._price_frame("BTC/USD:USD")
        if btc_df is None:
            self._xsr_pair_cache = {}
            self._xsr_cache_signature = signature
            return

        momo_lb = max(2, int(self.buy_xsr_momo_lookback.value))
        rev_lb = max(2, int(self.buy_xsr_reversal_lookback.value))
        relvol_len = max(4, int(self.buy_xsr_relvol_len.value))
        ema_fast_len = max(4, int(self.buy_xsr_ema_fast.value))
        ema_slow_len = max(ema_fast_len + 1, int(self.buy_xsr_ema_slow.value))

        btc_close = pd.to_numeric(btc_df.get("close"), errors="coerce")
        btc_momo = pd.Series(btc_close.pct_change(momo_lb).to_numpy(), index=btc_df["__date"])
        btc_rev = pd.Series(btc_close.pct_change(rev_lb).to_numpy(), index=btc_df["__date"])

        pair_frames: dict[str, pd.DataFrame] = {}
        for pair in pairs:
            base_df = self._price_frame(pair)
            if base_df is None:
                continue
            close = pd.to_numeric(base_df.get("close"), errors="coerce")
            high = pd.to_numeric(base_df.get("high"), errors="coerce")
            low = pd.to_numeric(base_df.get("low"), errors="coerce")
            volume = pd.to_numeric(base_df.get("volume"), errors="coerce")
            atr_pct = ta.ATR(base_df, timeperiod=14) / close.replace(0.0, np.nan)
            relvol = volume / volume.rolling(relvol_len, min_periods=max(3, relvol_len // 3)).mean().replace(0.0, np.nan)
            ema_fast = ta.EMA(base_df, timeperiod=ema_fast_len)
            ema_slow = ta.EMA(base_df, timeperiod=ema_slow_len)
            pair_momo = close.pct_change(momo_lb)
            pair_rev = close.pct_change(rev_lb)
            idx = base_df["__date"]
            rel_momo = pd.Series(pair_momo.to_numpy(), index=idx) - btc_momo.reindex(idx).ffill()
            reversal = -(pd.Series(pair_rev.to_numpy(), index=idx) - btc_rev.reindex(idx).ffill())
            funding = pd.Series(self._funding_series(base_df, pair).to_numpy(), index=idx)
            basis = pd.Series(self._basis_series(base_df, pair).to_numpy(), index=idx)

            pair_frames[pair] = pd.DataFrame(
                {
                    "xsr_rel_momo": rel_momo,
                    "xsr_reversal": reversal,
                    "xsr_funding": -funding,
                    "xsr_basis": -basis,
                    "xsr_relvol": pd.Series(relvol.to_numpy(), index=idx),
                    "xsr_atr_pct": pd.Series(atr_pct.to_numpy(), index=idx),
                    "xsr_ema_fast": pd.Series(pd.to_numeric(ema_fast, errors="coerce").to_numpy(), index=idx),
                    "xsr_ema_slow": pd.Series(pd.to_numeric(ema_slow, errors="coerce").to_numpy(), index=idx),
                    "xsr_close": pd.Series(close.to_numpy(), index=idx),
                    "xsr_high": pd.Series(high.to_numpy(), index=idx),
                    "xsr_low": pd.Series(low.to_numpy(), index=idx),
                }
            ).sort_index()

        if len(pair_frames) < 4:
            self._xsr_pair_cache = {}
            self._xsr_cache_signature = signature
            return

        momo_mat = pd.DataFrame({pair: frame["xsr_rel_momo"] for pair, frame in pair_frames.items()}).sort_index()
        rev_mat = pd.DataFrame({pair: frame["xsr_reversal"] for pair, frame in pair_frames.items()}).sort_index()
        funding_mat = pd.DataFrame({pair: frame["xsr_funding"] for pair, frame in pair_frames.items()}).sort_index()
        basis_mat = pd.DataFrame({pair: frame["xsr_basis"] for pair, frame in pair_frames.items()}).sort_index()
        relvol_mat = pd.DataFrame({pair: frame["xsr_relvol"] for pair, frame in pair_frames.items()}).sort_index()
        atr_mat = pd.DataFrame({pair: frame["xsr_atr_pct"] for pair, frame in pair_frames.items()}).sort_index()
        close_mat = pd.DataFrame({pair: frame["xsr_close"] for pair, frame in pair_frames.items()}).sort_index()
        ema_fast_mat = pd.DataFrame({pair: frame["xsr_ema_fast"] for pair, frame in pair_frames.items()}).sort_index()
        ema_slow_mat = pd.DataFrame({pair: frame["xsr_ema_slow"] for pair, frame in pair_frames.items()}).sort_index()

        disp_dev = (momo_mat.sub(momo_mat.median(axis=1), axis=0)).abs()
        disp_signed = np.sign(momo_mat).fillna(0.0) * disp_dev

        rank_momo = self._centered_rank_frame(momo_mat).fillna(0.0)
        rank_reversal = self._centered_rank_frame(rev_mat).fillna(0.0)
        rank_funding = self._centered_rank_frame(funding_mat).fillna(0.0)
        rank_basis = self._centered_rank_frame(basis_mat).fillna(0.0)
        rank_disp = self._centered_rank_frame(disp_signed).fillna(0.0)

        weights = {
            "momo": float(self.buy_xsr_w_momo.value),
            "reversal": float(self.buy_xsr_w_reversal.value),
            "basis": float(self.buy_xsr_w_basis.value),
            "funding": float(self.buy_xsr_w_funding.value),
            "dispersion": float(self.buy_xsr_w_dispersion.value),
        }
        weight_sum = sum(abs(v) for v in weights.values())
        if weight_sum <= 1e-9:
            weights["momo"] = 1.0
            weight_sum = 1.0

        score = (
            rank_momo * weights["momo"]
            + rank_reversal * weights["reversal"]
            + rank_basis * weights["basis"]
            + rank_funding * weights["funding"]
            + rank_disp * weights["dispersion"]
        ) / weight_sum

        long_rank = score.rank(axis=1, ascending=False, method="min")
        short_rank = score.rank(axis=1, ascending=True, method="min")
        long_selected = (long_rank <= int(self.buy_xsr_long_topn.value)) & (
            score >= float(self.buy_xsr_long_min_score.value)
        )
        short_selected = (short_rank <= int(self.buy_xsr_short_topn.value)) & (
            score <= -float(self.buy_xsr_short_min_score.value)
        )

        relvol_ok = relvol_mat >= float(self.buy_xsr_relvol_min.value)
        atr_ok = atr_mat <= float(self.buy_xsr_atr_pct_max.value)
        long_selected &= relvol_ok.fillna(False) & atr_ok.fillna(False)
        short_selected &= relvol_ok.fillna(False) & atr_ok.fillna(False)

        if bool(self.buy_xsr_require_ema_bias.value):
            long_selected &= ((close_mat > ema_fast_mat) & (ema_fast_mat > ema_slow_mat)).fillna(False)
            short_selected &= ((close_mat < ema_fast_mat) & (ema_fast_mat < ema_slow_mat)).fillna(False)

        cache: dict[str, pd.DataFrame] = {}
        for pair in pair_frames:
            cache[pair] = pd.DataFrame(
                {
                    "date": score.index,
                    "xsr_score": pd.to_numeric(score[pair], errors="coerce").values,
                    "xsr_momo_rank": pd.to_numeric(rank_momo[pair], errors="coerce").values,
                    "xsr_reversal_rank": pd.to_numeric(rank_reversal[pair], errors="coerce").values,
                    "xsr_basis_rank": pd.to_numeric(rank_basis[pair], errors="coerce").values,
                    "xsr_funding_rank": pd.to_numeric(rank_funding[pair], errors="coerce").values,
                    "xsr_dispersion_rank": pd.to_numeric(rank_disp[pair], errors="coerce").values,
                    "xsr_long_rank": pd.to_numeric(long_rank[pair], errors="coerce").values,
                    "xsr_short_rank": pd.to_numeric(short_rank[pair], errors="coerce").values,
                    "xsr_relvol": pd.to_numeric(relvol_mat[pair], errors="coerce").values,
                    "xsr_atr_pct": pd.to_numeric(atr_mat[pair], errors="coerce").values,
                    "xsr_long_selected": long_selected[pair].fillna(False).astype(bool).values,
                    "xsr_short_selected": short_selected[pair].fillna(False).astype(bool).values,
                }
            ).dropna(subset=["date"]).sort_values("date")

        self._xsr_pair_cache = cache
        self._xsr_cache_signature = signature

    def _merge_pair_cache(self, dataframe: DataFrame, pair: str) -> DataFrame:
        self._build_score_cache()
        cached = self._xsr_pair_cache.get(pair)
        if cached is None or cached.empty:
            return self._default_frame(dataframe.copy())

        left = dataframe.copy()
        left["__xsr_date"] = pd.to_datetime(left["date"], utc=True, errors="coerce")
        left = left.sort_values("__xsr_date")
        right = cached.copy().rename(columns={"date": "__xsr_date"}).sort_values("__xsr_date")
        merged = pd.merge_asof(left, right, on="__xsr_date", direction="backward")
        merged = merged.sort_index()
        merged.drop(columns=["__xsr_date"], inplace=True, errors="ignore")
        for col in ("xsr_long_selected", "xsr_short_selected"):
            merged[col] = merged[col].fillna(False).astype(bool)
        return merged

    def _pair_row_at_or_before_time(self, pair: str, when: datetime) -> pd.Series | None:
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            return None
        if dataframe is None or dataframe.empty or "date" not in dataframe.columns:
            return None
        ts = pd.Timestamp(when, tz="UTC")
        rows = dataframe.loc[pd.to_datetime(dataframe["date"], utc=True, errors="coerce") <= ts]
        if rows.empty:
            return None
        return rows.iloc[-1]

    def _open_xsr_side_count(self, is_short: bool) -> int:
        count = 0
        for trade in self._safe_get_open_trades():
            tag = str(getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or "")
            if not tag.startswith("xsr_"):
                continue
            if bool(getattr(trade, "is_short", False)) == is_short:
                count += 1
        return count

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not bool(self.buy_xsr_enabled.value):
            return self._default_frame(dataframe.copy())
        return self._merge_pair_cache(dataframe, metadata["pair"])

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "enter_long"] = 0
        dataframe.loc[:, "enter_short"] = 0
        dataframe.loc[:, "enter_tag"] = ""

        if not bool(self.buy_xsr_enabled.value):
            return dataframe

        base_mask = (dataframe["volume"] > 0).fillna(False)
        long_mask = dataframe.get("xsr_long_selected", False)
        if isinstance(long_mask, pd.Series):
            long_mask = long_mask.fillna(False).astype(bool)
        else:
            long_mask = pd.Series(False, index=dataframe.index, dtype=bool)
        short_mask = dataframe.get("xsr_short_selected", False)
        if isinstance(short_mask, pd.Series):
            short_mask = short_mask.fillna(False).astype(bool)
        else:
            short_mask = pd.Series(False, index=dataframe.index, dtype=bool)

        long_mask &= base_mask
        short_mask &= base_mask

        cooldown = max(1, int(self.buy_xsr_signal_cooldown_bars.value))
        long_recent = long_mask.shift(1).rolling(cooldown, min_periods=1).max().fillna(0).astype(bool)
        short_recent = short_mask.shift(1).rolling(cooldown, min_periods=1).max().fillna(0).astype(bool)
        long_mask &= ~long_recent
        short_mask &= ~short_recent

        rebalance_hours = max(1, int(self.buy_xsr_rebalance_hours.value))
        if rebalance_hours > 1:
            hours = pd.to_datetime(dataframe["date"], utc=True, errors="coerce").dt.hour
            eligible = hours.mod(rebalance_hours).eq(0).fillna(False)
            long_mask &= eligible
            short_mask &= eligible

        conflict = long_mask & short_mask
        long_mask &= ~conflict
        short_mask &= ~conflict

        dataframe.loc[long_mask, "enter_long"] = 1
        dataframe.loc[long_mask, "enter_tag"] = "xsr_long"
        dataframe.loc[short_mask, "enter_short"] = 1
        dataframe.loc[short_mask, "enter_tag"] = "xsr_short"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "exit_long"] = 0
        dataframe.loc[:, "exit_short"] = 0
        dataframe.loc[:, "exit_tag"] = ""
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        tag = str(entry_tag or "")
        if not tag.startswith("xsr_"):
            return True

        row = self._pair_row_at_or_before_time(pair, current_time)
        if row is None:
            return False

        if side == "long":
            if not bool(row.get("xsr_long_selected", False)):
                return False
            if self._open_xsr_side_count(False) >= int(self.buy_xsr_max_open_longs.value):
                return False
        else:
            if not bool(row.get("xsr_short_selected", False)):
                return False
            if self._open_xsr_side_count(True) >= int(self.buy_xsr_max_open_shorts.value):
                return False
        return True

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        tag = str(entry_tag or "")
        if not tag.startswith("xsr_"):
            return float(proposed_stake)

        total_slots = max(1, int(self.buy_xsr_long_topn.value) + int(self.buy_xsr_short_topn.value))
        base_cap = float(self._wallet_total()) * float(self.buy_xsr_gross_cap_pct.value) / float(total_slots)

        strength = 1.0
        row = self._pair_row_at_or_before_time(pair, current_time)
        if row is not None:
            score = abs(float(row.get("xsr_score", 0.0) or 0.0))
            threshold = float(self.buy_xsr_long_min_score.value if side == "long" else self.buy_xsr_short_min_score.value)
            threshold = max(0.05, threshold)
            strength = np.clip(
                score / threshold,
                float(self.buy_xsr_stake_floor_mult.value),
                float(self.buy_xsr_stake_ceiling_mult.value),
            )

        stake = min(float(proposed_stake), float(max_stake), float(base_cap) * float(strength))
        if min_stake is not None and stake < float(min_stake):
            return 0.0
        return max(0.0, float(stake))

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        lev = float(self.buy_xsr_leverage.value)
        return max(1.0, min(float(max_leverage), lev))

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        tag = str(getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or "")
        if not tag.startswith("xsr_"):
            return self.stoploss

        desired_open_profit = float(self.sell_xsr_stoploss.value)
        key = self._xsr_trade_key(trade)
        hwm = float(self._xsr_hwm.get(key, current_profit))
        if float(current_profit) > hwm:
            hwm = float(current_profit)
        self._xsr_hwm[key] = hwm

        if bool(self.sell_xsr_scratch_enabled.value) and hwm >= float(self.sell_xsr_scratch_arm.value):
            desired_open_profit = max(desired_open_profit, float(self.sell_xsr_scratch_stop.value))
        if bool(self.sell_xsr_trail_enabled.value) and hwm >= float(self.sell_xsr_trail_arm.value):
            desired_open_profit = max(desired_open_profit, hwm - float(self.sell_xsr_trail_offset.value))

        xsr_sl = stoploss_from_open(
            float(desired_open_profit),
            float(current_profit),
            is_short=trade.is_short,
            leverage=trade.leverage,
        )
        return float(xsr_sl) if xsr_sl is not None else 1.0

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | None:
        tag = str(getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or "")
        if not tag.startswith("xsr_"):
            return None

        row = self._pair_row_at_or_before_time(pair, current_time)
        age_min = 0.0
        try:
            age_min = (current_time - trade.open_date_utc).total_seconds() / 60.0
        except Exception:
            pass

        if row is not None:
            score = float(row.get("xsr_score", np.nan))
            long_rank = float(row.get("xsr_long_rank", np.nan))
            short_rank = float(row.get("xsr_short_rank", np.nan))
            exit_rank = float(self.sell_xsr_rank_exit.value)
            exit_score = float(self.sell_xsr_score_exit.value)

            if not trade.is_short:
                if bool(row.get("xsr_short_selected", False)):
                    return "xsr_flip"
                if np.isfinite(long_rank) and long_rank > exit_rank:
                    return "xsr_rank_exit"
                if np.isfinite(score) and score <= exit_score:
                    return "xsr_score_exit"
            else:
                if bool(row.get("xsr_long_selected", False)):
                    return "xsr_flip"
                if np.isfinite(short_rank) and short_rank > exit_rank:
                    return "xsr_rank_exit"
                if np.isfinite(score) and score >= -exit_score:
                    return "xsr_score_exit"

        if current_profit >= float(self.sell_xsr_profit_target.value):
            return "xsr_tp"

        if age_min >= float(self.sell_xsr_time_stop_minutes.value):
            return "xsr_time_stop"

        return None
