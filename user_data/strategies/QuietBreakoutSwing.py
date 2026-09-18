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
from market_context import derivative_candle_types, reference_pair


logger = logging.getLogger(__name__)

_REF_BTC = "BTC/USDT:USDT"
_REF_ETH = "ETH/USDT:USDT"

_TAIL_PAIRS = {
    "PEPE/USDT:USDT",
    "BONK/USDT:USDT",
    "SEI/USDT:USDT",
    "WLD/USDT:USDT",
}

_UNAVAILABLE_PAIRS = {
    "FET/USDT:USDT",
    "RNDR/USDT:USDT",
}

_MAJORS_PAIRS = {
    "DOGE/USDT:USDT",
    "ADA/USDT:USDT",
    "LINK/USDT:USDT",
    "DOT/USDT:USDT",
    "NEAR/USDT:USDT",
    "UNI/USDT:USDT",
    "ATOM/USDT:USDT",
    "FIL/USDT:USDT",
    "LTC/USDT:USDT",
    "ARB/USDT:USDT",
    "OP/USDT:USDT",
    "TRX/USDT:USDT",
    "ETC/USDT:USDT",
    "AAVE/USDT:USDT",
    "INJ/USDT:USDT",
    "TIA/USDT:USDT",
    "JUP/USDT:USDT",
}

_TREND_CORE4_PAIRS = {
    "TRX/USDT:USDT",
    "DOT/USDT:USDT",
    "ATOM/USDT:USDT",
    "NEAR/USDT:USDT",
}


class QuietBreakoutSwing(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "4h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 420
    position_adjustment_enable = False
    use_custom_stoploss = True
    stoploss = -0.20
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

    buy_qbs_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_qbs_universe_profile = CategoricalParameter(
        ["full", "liquid_alts", "majors", "trend_core4"],
        default="liquid_alts",
        space="buy",
        optimize=False,
        load=True,
    )
    buy_qbs_rebalance_hours = IntParameter(4, 24, default=8, space="buy", optimize=False, load=True)
    buy_qbs_signal_cooldown_bars = IntParameter(1, 8, default=2, space="buy", optimize=False, load=True)
    buy_qbs_long_topn = IntParameter(1, 4, default=1, space="buy", optimize=True, load=True)
    buy_qbs_max_open_longs = IntParameter(1, 4, default=1, space="buy", optimize=False, load=True)
    buy_qbs_fast_lookback = IntParameter(4, 24, default=8, space="buy", optimize=False, load=True)
    buy_qbs_slow_lookback = IntParameter(18, 120, default=30, space="buy", optimize=False, load=True)
    buy_qbs_breakout_lookback = IntParameter(8, 36, default=20, space="buy", optimize=False, load=True)
    buy_qbs_breakout_recent_bars = IntParameter(1, 8, default=3, space="buy", optimize=True, load=True)
    buy_qbs_quiet_recent_bars = IntParameter(1, 12, default=6, space="buy", optimize=True, load=True)
    buy_qbs_volx_recent_bars = IntParameter(1, 8, default=3, space="buy", optimize=True, load=True)
    buy_qbs_rank_persistence_bars = IntParameter(1, 6, default=2, space="buy", optimize=True, load=True)
    buy_qbs_relvol_len = IntParameter(6, 48, default=18, space="buy", optimize=False, load=True)
    buy_qbs_relvol_min = DecimalParameter(0.80, 2.20, default=0.90, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_volx_min = DecimalParameter(0.70, 2.20, default=1.00, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_atr_pct_max = DecimalParameter(0.010, 0.20, default=0.080, decimals=3, space="buy", optimize=True, load=True)
    buy_qbs_quiet_atr_ratio_max = DecimalParameter(0.50, 1.80, default=1.05, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_quiet_bb_ratio_max = DecimalParameter(0.50, 1.80, default=1.05, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_breakout_min = DecimalParameter(0.000, 0.040, default=0.002, decimals=3, space="buy", optimize=True, load=True)
    buy_qbs_require_quiet_prebreakout = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_qbs_eth_lead_min = DecimalParameter(0.000, 0.060, default=0.003, decimals=3, space="buy", optimize=True, load=True)
    buy_qbs_min_score = DecimalParameter(0.05, 0.80, default=0.12, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_w_fast = DecimalParameter(0.0, 1.0, default=0.35, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_w_slow = DecimalParameter(0.0, 1.0, default=0.45, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_w_breakout = DecimalParameter(0.0, 1.0, default=0.20, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_require_pair_4h_bias = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_qbs_require_pair_1d_bias = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_qbs_require_btc_1d_bias = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_qbs_require_eth_lead = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_qbs_ema_fast = IntParameter(12, 72, default=24, space="buy", optimize=False, load=True)
    buy_qbs_ema_slow = IntParameter(24, 200, default=96, space="buy", optimize=False, load=True)
    buy_qbs_ema1d_fast = IntParameter(10, 80, default=30, space="buy", optimize=False, load=True)
    buy_qbs_ema1d_slow = IntParameter(30, 250, default=90, space="buy", optimize=False, load=True)
    buy_qbs_gross_cap_pct = DecimalParameter(0.05, 0.60, default=0.28, decimals=2, space="buy", optimize=False, load=True)
    buy_qbs_stake_floor_mult = DecimalParameter(0.50, 1.00, default=0.80, decimals=2, space="buy", optimize=False, load=True)
    buy_qbs_stake_ceiling_mult = DecimalParameter(1.00, 1.80, default=1.30, decimals=2, space="buy", optimize=False, load=True)
    buy_qbs_leverage = DecimalParameter(1.0, 3.0, default=1.0, decimals=1, space="buy", optimize=False, load=True)
    buy_qbs_carry_enabled = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_qbs_carry_w_basis = DecimalParameter(0.0, 1.0, default=0.12, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_carry_w_funding = DecimalParameter(0.0, 1.0, default=0.08, decimals=2, space="buy", optimize=True, load=True)
    buy_qbs_debug = BooleanParameter(default=False, space="buy", optimize=False, load=True)

    sell_qbs_stoploss = DecimalParameter(-0.12, -0.01, default=-0.050, decimals=3, space="sell", optimize=True, load=True)
    sell_qbs_profit_target = DecimalParameter(0.01, 0.20, default=0.080, decimals=3, space="sell", optimize=True, load=True)
    sell_qbs_time_stop_hours = IntParameter(24, 240, default=168, space="sell", optimize=True, load=True)
    sell_qbs_rank_exit = IntParameter(2, 12, default=4, space="sell", optimize=True, load=True)
    sell_qbs_score_exit = DecimalParameter(-0.10, 0.20, default=0.01, decimals=2, space="sell", optimize=True, load=True)
    sell_qbs_macro_exit = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_qbs_scratch_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_qbs_scratch_arm = DecimalParameter(0.005, 0.06, default=0.020, decimals=3, space="sell", optimize=True, load=True)
    sell_qbs_scratch_stop = DecimalParameter(-0.010, 0.02, default=0.002, decimals=3, space="sell", optimize=True, load=True)
    sell_qbs_trail_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_qbs_trail_arm = DecimalParameter(0.010, 0.12, default=0.040, decimals=3, space="sell", optimize=True, load=True)
    sell_qbs_trail_offset = DecimalParameter(0.004, 0.08, default=0.018, decimals=3, space="sell", optimize=True, load=True)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._ref_btc = reference_pair("BTC", config)
        self._ref_eth = reference_pair("ETH", config)
        self._qbs_pair_cache: dict[str, pd.DataFrame] = {}
        self._qbs_cache_signature: tuple[Any, ...] | None = None
        self._qbs_hwm: dict[str, float] = {}

    def informative_pairs(self):
        if not bool(self.buy_qbs_enabled.value):
            return []
        result: list[tuple[str, str] | tuple[str, str, str]] = []
        pairset = set(self._qbs_pairs()) | {self._ref_btc, self._ref_eth}
        for pair in sorted(pairset):
            result.append((pair, "1d"))
            for candle_type in derivative_candle_types(self.config):
                result.append((pair, self.timeframe if candle_type != "funding_rate" else "1h", candle_type))
        return result

    def _qbs_pairs(self) -> list[str]:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = list(self.config.get("exchange", {}).get("pair_whitelist", []))
        profile = str(self.buy_qbs_universe_profile.value or "liquid_alts")
        out: list[str] = []
        for pair in pairs:
            if pair in {_REF_BTC, _REF_ETH} | _UNAVAILABLE_PAIRS:
                continue
            if profile == "liquid_alts" and pair in _TAIL_PAIRS:
                continue
            if profile == "majors" and pair not in _MAJORS_PAIRS:
                continue
            if profile == "trend_core4" and pair not in _TREND_CORE4_PAIRS:
                continue
            out.append(pair)
        return out

    def _qbs_signature(self) -> tuple[Any, ...]:
        return (
            tuple(sorted(self._qbs_pairs())),
            int(self.buy_qbs_fast_lookback.value),
            int(self.buy_qbs_slow_lookback.value),
            int(self.buy_qbs_breakout_lookback.value),
            int(self.buy_qbs_breakout_recent_bars.value),
            int(self.buy_qbs_quiet_recent_bars.value),
            int(self.buy_qbs_volx_recent_bars.value),
            int(self.buy_qbs_rank_persistence_bars.value),
            int(self.buy_qbs_relvol_len.value),
            int(self.buy_qbs_rebalance_hours.value),
            int(self.buy_qbs_signal_cooldown_bars.value),
            int(self.buy_qbs_ema_fast.value),
            int(self.buy_qbs_ema_slow.value),
            int(self.buy_qbs_ema1d_fast.value),
            int(self.buy_qbs_ema1d_slow.value),
            float(self.buy_qbs_relvol_min.value),
            float(self.buy_qbs_volx_min.value),
            float(self.buy_qbs_atr_pct_max.value),
            float(self.buy_qbs_quiet_atr_ratio_max.value),
            float(self.buy_qbs_quiet_bb_ratio_max.value),
            float(self.buy_qbs_breakout_min.value),
            float(self.buy_qbs_eth_lead_min.value),
            float(self.buy_qbs_min_score.value),
            float(self.buy_qbs_w_fast.value),
            float(self.buy_qbs_w_slow.value),
            float(self.buy_qbs_w_breakout.value),
            float(self.buy_qbs_carry_w_basis.value),
            float(self.buy_qbs_carry_w_funding.value),
            int(self.buy_qbs_long_topn.value),
            bool(self.buy_qbs_require_pair_4h_bias.value),
            bool(self.buy_qbs_require_pair_1d_bias.value),
            bool(self.buy_qbs_require_btc_1d_bias.value),
            bool(self.buy_qbs_require_eth_lead.value),
            bool(self.buy_qbs_require_quiet_prebreakout.value),
            bool(self.buy_qbs_carry_enabled.value),
        )

    def _default_frame(self, dataframe: DataFrame) -> DataFrame:
        defaults = {
            "qbs_base_score": np.nan,
            "qbs_carry_score": np.nan,
            "qbs_score": np.nan,
            "qbs_fast_rank": np.nan,
            "qbs_slow_rank": np.nan,
            "qbs_breakout_rank": np.nan,
            "qbs_long_rank": np.nan,
            "qbs_relvol": np.nan,
            "qbs_volx": np.nan,
            "qbs_atr_pct": np.nan,
            "qbs_quiet_atr_ratio": np.nan,
            "qbs_quiet_bb_ratio": np.nan,
            "qbs_basis": np.nan,
            "qbs_funding": np.nan,
            "qbs_eth_lead": np.nan,
            "qbs_pair_1d_bias": False,
            "qbs_btc_1d_bias": False,
            "qbs_breakout_ok": False,
            "qbs_breakout_recent": False,
            "qbs_quiet_recent": False,
            "qbs_volx_recent": False,
            "qbs_long_selected": False,
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
            wallet_total = float(self.wallets.get_total(self.config.get("stake_currency", "USDT")))
            if wallet_total > 0:
                return wallet_total
        except Exception:
            pass
        try:
            return float(self.config.get("dry_run_wallet", 1000))
        except Exception:
            return 1000.0

    def _qbs_trade_key(self, trade: Trade) -> str:
        return f"{getattr(trade, 'id', 'na')}|{getattr(trade, 'pair', '')}|{getattr(trade, 'open_date_utc', '')}"

    def _price_frame(self, pair: str, timeframe: str) -> pd.DataFrame | None:
        try:
            df = self.dp.get_pair_dataframe(pair=pair, timeframe=timeframe)
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
            fr_df = self.dp.get_pair_dataframe(pair=pair, timeframe="1h", candle_type="funding_rate")
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
        work["__funding"] = funding
        merged = self._merge_asof_numeric_series(base_df, work, "__funding")
        return merged.rolling(6, min_periods=2).mean()

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
            work["__mark_close"] = pd.to_numeric(work.get("close"), errors="coerce")
            mark = self._merge_asof_numeric_series(base_df, work, "__mark_close")

        index = pd.Series(np.nan, index=base_df.index, dtype=float)
        if index_df is not None and not index_df.empty:
            work = index_df.copy()
            work["__date"] = pd.to_datetime(work["date"], utc=True, errors="coerce")
            work["__index_close"] = pd.to_numeric(work.get("close"), errors="coerce")
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
        if not bool(self.buy_qbs_enabled.value):
            self._qbs_pair_cache = {}
            self._qbs_cache_signature = self._qbs_signature()
            return

        signature = self._qbs_signature()
        if self._qbs_cache_signature == signature and self._qbs_pair_cache:
            return

        pairs = self._qbs_pairs()
        if len(pairs) < 4:
            self._qbs_pair_cache = {}
            self._qbs_cache_signature = signature
            return

        btc_df = self._price_frame(self._ref_btc, self.timeframe)
        eth_df = self._price_frame(self._ref_eth, self.timeframe)
        btc_1d_df = self._price_frame(self._ref_btc, "1d")
        if btc_df is None or eth_df is None or btc_1d_df is None:
            self._qbs_pair_cache = {}
            self._qbs_cache_signature = signature
            return

        fast_lb = max(2, int(self.buy_qbs_fast_lookback.value))
        slow_lb = max(fast_lb + 2, int(self.buy_qbs_slow_lookback.value))
        quiet_lb = max(10, int(self.buy_qbs_slow_lookback.value))
        breakout_lb = max(2, int(self.buy_qbs_breakout_lookback.value))
        relvol_len = max(4, int(self.buy_qbs_relvol_len.value))
        ema_fast_len = max(4, int(self.buy_qbs_ema_fast.value))
        ema_slow_len = max(ema_fast_len + 1, int(self.buy_qbs_ema_slow.value))
        ema1d_fast_len = max(4, int(self.buy_qbs_ema1d_fast.value))
        ema1d_slow_len = max(ema1d_fast_len + 1, int(self.buy_qbs_ema1d_slow.value))

        btc_close = pd.to_numeric(btc_df.get("close"), errors="coerce")
        eth_close = pd.to_numeric(eth_df.get("close"), errors="coerce")
        btc_fast = pd.Series(btc_close.pct_change(fast_lb).to_numpy(), index=btc_df["__date"])
        eth_fast = pd.Series(eth_close.pct_change(fast_lb).to_numpy(), index=eth_df["__date"])
        btc_slow = pd.Series(btc_close.pct_change(slow_lb).to_numpy(), index=btc_df["__date"])
        eth_slow = pd.Series(eth_close.pct_change(slow_lb).to_numpy(), index=eth_df["__date"])
        btc_ema1d_fast = ta.EMA(btc_1d_df, timeperiod=ema1d_fast_len)
        btc_ema1d_slow = ta.EMA(btc_1d_df, timeperiod=ema1d_slow_len)
        btc_1d_close = pd.to_numeric(btc_1d_df.get("close"), errors="coerce")
        btc_1d_bias = pd.Series(
            ((btc_1d_close > pd.to_numeric(btc_ema1d_fast, errors="coerce"))
             & (pd.to_numeric(btc_ema1d_fast, errors="coerce") > pd.to_numeric(btc_ema1d_slow, errors="coerce"))).to_numpy(),
            index=btc_1d_df["__date"],
        )

        pair_frames: dict[str, pd.DataFrame] = {}
        for pair in pairs:
            base_df = self._price_frame(pair, self.timeframe)
            daily_df = self._price_frame(pair, "1d")
            if base_df is None or daily_df is None:
                continue

            close = pd.to_numeric(base_df.get("close"), errors="coerce")
            high = pd.to_numeric(base_df.get("high"), errors="coerce")
            volume = pd.to_numeric(base_df.get("volume"), errors="coerce")
            atr_pct = ta.ATR(base_df, timeperiod=14) / close.replace(0.0, np.nan)
            relvol = volume / volume.rolling(relvol_len, min_periods=max(3, relvol_len // 3)).mean().replace(0.0, np.nan)
            ema_fast = ta.EMA(base_df, timeperiod=ema_fast_len)
            ema_slow = ta.EMA(base_df, timeperiod=ema_slow_len)
            pair_fast = close.pct_change(fast_lb)
            pair_slow = close.pct_change(slow_lb)
            quiet_atr_base = atr_pct.rolling(quiet_lb, min_periods=max(4, quiet_lb // 3)).median().replace(0.0, np.nan)
            quiet_atr_ratio = atr_pct / quiet_atr_base
            bb_mid = close.rolling(quiet_lb, min_periods=max(4, quiet_lb // 3)).mean()
            bb_std = close.rolling(quiet_lb, min_periods=max(4, quiet_lb // 3)).std(ddof=0)
            bb_width = ((bb_std * 4.0) / bb_mid.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
            quiet_bb_base = bb_width.rolling(quiet_lb, min_periods=max(4, quiet_lb // 3)).median().replace(0.0, np.nan)
            quiet_bb_ratio = bb_width / quiet_bb_base
            quiet_raw = (-(quiet_atr_ratio + quiet_bb_ratio) / 2.0).replace([np.inf, -np.inf], np.nan)

            idx = base_df["__date"]
            bench_fast = (btc_fast.reindex(idx).ffill() + eth_fast.reindex(idx).ffill()) / 2.0
            bench_slow = (btc_slow.reindex(idx).ffill() + eth_slow.reindex(idx).ffill()) / 2.0
            excess_fast = pd.Series(pair_fast.to_numpy(), index=idx) - bench_fast
            excess_slow = pd.Series(pair_slow.to_numpy(), index=idx) - bench_slow
            breakout_ref = high.rolling(breakout_lb).max().shift(1)
            breakout_raw = ((close / breakout_ref.replace(0.0, np.nan)) - 1.0).replace([np.inf, -np.inf], np.nan)
            breakout_ok = (breakout_raw >= float(self.buy_qbs_breakout_min.value)).fillna(False)
            eth_lead = (eth_fast.reindex(idx).ffill() - btc_fast.reindex(idx).ffill()).replace([np.inf, -np.inf], np.nan)
            basis = pd.Series(self._basis_series(base_df, pair).to_numpy(), index=idx)
            funding = pd.Series(self._funding_series(base_df, pair).to_numpy(), index=idx)

            daily_close = pd.to_numeric(daily_df.get("close"), errors="coerce")
            daily_ema_fast = pd.to_numeric(ta.EMA(daily_df, timeperiod=ema1d_fast_len), errors="coerce")
            daily_ema_slow = pd.to_numeric(ta.EMA(daily_df, timeperiod=ema1d_slow_len), errors="coerce")
            daily_bias_df = daily_df[["__date"]].copy()
            daily_bias_df["__pair_1d_bias"] = (
                (daily_close > daily_ema_fast) & (daily_ema_fast > daily_ema_slow)
            ).astype(float)
            pair_1d_bias = self._merge_asof_numeric_series(base_df, daily_bias_df, "__pair_1d_bias") >= 0.5
            btc_bias_df = btc_1d_df[["__date"]].copy()
            btc_bias_df["__btc_1d_bias"] = btc_1d_bias.astype(float).values
            btc_bias_m = self._merge_asof_numeric_series(base_df, btc_bias_df, "__btc_1d_bias") >= 0.5

            pair_frames[pair] = pd.DataFrame(
                {
                    "qbs_excess_fast": excess_fast,
                    "qbs_excess_slow": excess_slow,
                    "qbs_breakout_raw": pd.Series(breakout_raw.to_numpy(), index=idx),
                    "qbs_breakout_ok": pd.Series(breakout_ok.to_numpy(), index=idx).astype(bool),
                    "qbs_eth_lead": eth_lead,
                    "qbs_basis": -basis,
                    "qbs_funding": -funding,
                    "qbs_quiet_raw": pd.Series(quiet_raw.to_numpy(), index=idx),
                    "qbs_quiet_atr_ratio": pd.Series(quiet_atr_ratio.to_numpy(), index=idx),
                    "qbs_quiet_bb_ratio": pd.Series(quiet_bb_ratio.to_numpy(), index=idx),
                    "qbs_relvol": pd.Series(relvol.to_numpy(), index=idx),
                    "qbs_volx": pd.Series(relvol.to_numpy(), index=idx),
                    "qbs_atr_pct": pd.Series(atr_pct.to_numpy(), index=idx),
                    "qbs_close": pd.Series(close.to_numpy(), index=idx),
                    "qbs_ema_fast": pd.Series(pd.to_numeric(ema_fast, errors="coerce").to_numpy(), index=idx),
                    "qbs_ema_slow": pd.Series(pd.to_numeric(ema_slow, errors="coerce").to_numpy(), index=idx),
                    "qbs_pair_1d_bias": pd.Series(pair_1d_bias.to_numpy(), index=idx).astype(bool),
                    "qbs_btc_1d_bias": pd.Series(btc_bias_m.to_numpy(), index=idx).astype(bool),
                }
            ).sort_index()

        if len(pair_frames) < 4:
            self._qbs_pair_cache = {}
            self._qbs_cache_signature = signature
            return

        fast_mat = pd.DataFrame({pair: frame["qbs_excess_fast"] for pair, frame in pair_frames.items()}).sort_index()
        slow_mat = pd.DataFrame({pair: frame["qbs_quiet_raw"] for pair, frame in pair_frames.items()}).sort_index()
        breakout_mat = pd.DataFrame({pair: frame["qbs_breakout_raw"] for pair, frame in pair_frames.items()}).sort_index()
        basis_mat = pd.DataFrame({pair: frame["qbs_basis"] for pair, frame in pair_frames.items()}).sort_index()
        funding_mat = pd.DataFrame({pair: frame["qbs_funding"] for pair, frame in pair_frames.items()}).sort_index()
        relvol_mat = pd.DataFrame({pair: frame["qbs_relvol"] for pair, frame in pair_frames.items()}).sort_index()
        volx_mat = pd.DataFrame({pair: frame["qbs_volx"] for pair, frame in pair_frames.items()}).sort_index()
        atr_mat = pd.DataFrame({pair: frame["qbs_atr_pct"] for pair, frame in pair_frames.items()}).sort_index()
        quiet_atr_ratio_mat = pd.DataFrame({pair: frame["qbs_quiet_atr_ratio"] for pair, frame in pair_frames.items()}).sort_index()
        quiet_bb_ratio_mat = pd.DataFrame({pair: frame["qbs_quiet_bb_ratio"] for pair, frame in pair_frames.items()}).sort_index()
        close_mat = pd.DataFrame({pair: frame["qbs_close"] for pair, frame in pair_frames.items()}).sort_index()
        ema_fast_mat = pd.DataFrame({pair: frame["qbs_ema_fast"] for pair, frame in pair_frames.items()}).sort_index()
        ema_slow_mat = pd.DataFrame({pair: frame["qbs_ema_slow"] for pair, frame in pair_frames.items()}).sort_index()
        breakout_ok_mat = pd.DataFrame({pair: frame["qbs_breakout_ok"] for pair, frame in pair_frames.items()}).sort_index()
        pair_1d_bias_mat = pd.DataFrame({pair: frame["qbs_pair_1d_bias"] for pair, frame in pair_frames.items()}).sort_index()
        btc_1d_bias_mat = pd.DataFrame({pair: frame["qbs_btc_1d_bias"] for pair, frame in pair_frames.items()}).sort_index()
        eth_lead_mat = pd.DataFrame({pair: frame["qbs_eth_lead"] for pair, frame in pair_frames.items()}).sort_index()

        rank_fast = self._centered_rank_frame(fast_mat).fillna(0.0)
        rank_slow = self._centered_rank_frame(slow_mat).fillna(0.0)
        rank_breakout = self._centered_rank_frame(breakout_mat.clip(lower=-0.20, upper=0.20)).fillna(0.0)
        rank_basis = self._centered_rank_frame(basis_mat).fillna(0.0)
        rank_funding = self._centered_rank_frame(funding_mat).fillna(0.0)

        base_weights = {
            "fast": float(self.buy_qbs_w_fast.value),
            "slow": float(self.buy_qbs_w_slow.value),
            "breakout": float(self.buy_qbs_w_breakout.value),
        }
        base_wsum = sum(abs(v) for v in base_weights.values()) or 1.0
        base_score = (
            rank_fast * base_weights["fast"]
            + rank_slow * base_weights["slow"]
            + rank_breakout * base_weights["breakout"]
        ) / base_wsum

        carry_weights = {
            "basis": float(self.buy_qbs_carry_w_basis.value),
            "funding": float(self.buy_qbs_carry_w_funding.value),
        }
        carry_wsum = sum(abs(v) for v in carry_weights.values()) or 1.0
        carry_score = (
            rank_basis * carry_weights["basis"]
            + rank_funding * carry_weights["funding"]
        ) / carry_wsum

        if bool(self.buy_qbs_carry_enabled.value):
            score = base_score + carry_score
        else:
            score = base_score

        long_rank = score.rank(axis=1, ascending=False, method="min")
        topn = int(self.buy_qbs_long_topn.value)
        long_selected = (long_rank <= topn) & (score >= float(self.buy_qbs_min_score.value))

        relvol_ok = relvol_mat >= float(self.buy_qbs_relvol_min.value)
        atr_ok = atr_mat <= float(self.buy_qbs_atr_pct_max.value)
        quiet_ok = (
            (quiet_atr_ratio_mat <= float(self.buy_qbs_quiet_atr_ratio_max.value))
            & (quiet_bb_ratio_mat <= float(self.buy_qbs_quiet_bb_ratio_max.value))
        )
        volx_ok = volx_mat >= float(self.buy_qbs_volx_min.value)
        breakout_recent_bars = max(1, int(self.buy_qbs_breakout_recent_bars.value))
        quiet_recent_bars = max(1, int(self.buy_qbs_quiet_recent_bars.value))
        volx_recent_bars = max(1, int(self.buy_qbs_volx_recent_bars.value))

        breakout_recent = breakout_ok_mat.rolling(breakout_recent_bars, min_periods=1).max().fillna(0.0) >= 1.0
        volx_recent = volx_ok.rolling(volx_recent_bars, min_periods=1).max().fillna(0.0) >= 1.0
        quiet_recent = quiet_ok.shift(1).rolling(quiet_recent_bars, min_periods=1).max().fillna(0.0) >= 1.0

        long_selected &= relvol_ok.fillna(False) & atr_ok.fillna(False) & breakout_recent.fillna(False) & volx_recent.fillna(False)
        if bool(self.buy_qbs_require_quiet_prebreakout.value):
            long_selected &= quiet_recent.fillna(False)

        if bool(self.buy_qbs_require_pair_4h_bias.value):
            long_selected &= ((close_mat > ema_fast_mat) & (ema_fast_mat > ema_slow_mat)).fillna(False)
        if bool(self.buy_qbs_require_pair_1d_bias.value):
            long_selected &= pair_1d_bias_mat.fillna(False)
        if bool(self.buy_qbs_require_btc_1d_bias.value):
            long_selected &= btc_1d_bias_mat.fillna(False)
        if bool(self.buy_qbs_require_eth_lead.value):
            long_selected &= (eth_lead_mat >= float(self.buy_qbs_eth_lead_min.value)).fillna(False)

        persistence = max(1, int(self.buy_qbs_rank_persistence_bars.value))
        if persistence > 1:
            persist_ok = (long_rank <= (topn + 1)).rolling(persistence, min_periods=persistence).sum() >= persistence
            long_selected &= persist_ok.fillna(False)

        cache: dict[str, pd.DataFrame] = {}
        for pair in pair_frames:
            cache[pair] = pd.DataFrame(
                {
                    "date": score.index,
                    "qbs_base_score": pd.to_numeric(base_score[pair], errors="coerce").values,
                    "qbs_carry_score": pd.to_numeric(carry_score[pair], errors="coerce").values,
                    "qbs_score": pd.to_numeric(score[pair], errors="coerce").values,
                    "qbs_fast_rank": pd.to_numeric(rank_fast[pair], errors="coerce").values,
                    "qbs_slow_rank": pd.to_numeric(rank_slow[pair], errors="coerce").values,
                    "qbs_breakout_rank": pd.to_numeric(rank_breakout[pair], errors="coerce").values,
                    "qbs_long_rank": pd.to_numeric(long_rank[pair], errors="coerce").values,
                    "qbs_relvol": pd.to_numeric(relvol_mat[pair], errors="coerce").values,
                    "qbs_volx": pd.to_numeric(volx_mat[pair], errors="coerce").values,
                    "qbs_atr_pct": pd.to_numeric(atr_mat[pair], errors="coerce").values,
                    "qbs_quiet_atr_ratio": pd.to_numeric(quiet_atr_ratio_mat[pair], errors="coerce").values,
                    "qbs_quiet_bb_ratio": pd.to_numeric(quiet_bb_ratio_mat[pair], errors="coerce").values,
                    "qbs_basis": pd.to_numeric((-basis_mat[pair]), errors="coerce").values,
                    "qbs_funding": pd.to_numeric((-funding_mat[pair]), errors="coerce").values,
                    "qbs_eth_lead": pd.to_numeric(eth_lead_mat[pair], errors="coerce").values,
                    "qbs_pair_1d_bias": pair_1d_bias_mat[pair].fillna(False).astype(bool).values,
                    "qbs_btc_1d_bias": btc_1d_bias_mat[pair].fillna(False).astype(bool).values,
                    "qbs_breakout_ok": breakout_ok_mat[pair].fillna(False).astype(bool).values,
                    "qbs_breakout_recent": breakout_recent[pair].fillna(False).astype(bool).values,
                    "qbs_quiet_recent": quiet_recent[pair].fillna(False).astype(bool).values,
                    "qbs_volx_recent": volx_recent[pair].fillna(False).astype(bool).values,
                    "qbs_long_selected": long_selected[pair].fillna(False).astype(bool).values,
                }
            ).dropna(subset=["date"]).sort_values("date")

        self._qbs_pair_cache = cache
        self._qbs_cache_signature = signature

    def _merge_pair_cache(self, dataframe: DataFrame, pair: str) -> DataFrame:
        self._build_score_cache()
        cached = self._qbs_pair_cache.get(pair)
        if cached is None or cached.empty:
            return self._default_frame(dataframe.copy())

        left = dataframe.copy()
        left["__qbs_date"] = pd.to_datetime(left["date"], utc=True, errors="coerce")
        left = left.sort_values("__qbs_date")
        right = cached.copy().rename(columns={"date": "__qbs_date"}).sort_values("__qbs_date")
        merged = pd.merge_asof(left, right, on="__qbs_date", direction="backward")
        merged = merged.sort_index()
        merged.drop(columns=["__qbs_date"], inplace=True, errors="ignore")
        for col in (
            "qbs_pair_1d_bias",
            "qbs_btc_1d_bias",
            "qbs_breakout_ok",
            "qbs_breakout_recent",
            "qbs_quiet_recent",
            "qbs_volx_recent",
            "qbs_long_selected",
        ):
            merged[col] = merged[col].fillna(False).astype(bool)
        return merged

    def _pair_row_at_or_before_time(self, pair: str, when: datetime) -> pd.Series | None:
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            return None
        if dataframe is None or dataframe.empty or "date" not in dataframe.columns:
            return None
        ts = pd.Timestamp(when)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        rows = dataframe.loc[pd.to_datetime(dataframe["date"], utc=True, errors="coerce") <= ts]
        if rows.empty:
            return None
        return rows.iloc[-1]

    def _open_qbs_count(self) -> int:
        count = 0
        for trade in self._safe_get_open_trades():
            tag = str(getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or "")
            if tag.startswith("qbs_") and not bool(getattr(trade, "is_short", False)):
                count += 1
        return count

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not bool(self.buy_qbs_enabled.value):
            return self._default_frame(dataframe.copy())
        return self._merge_pair_cache(dataframe, metadata["pair"])

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "enter_long"] = 0
        dataframe.loc[:, "enter_short"] = 0
        dataframe.loc[:, "enter_tag"] = ""

        if not bool(self.buy_qbs_enabled.value):
            return dataframe

        base_mask = (dataframe["volume"] > 0).fillna(False)
        long_mask = dataframe.get("qbs_long_selected", False)
        if isinstance(long_mask, pd.Series):
            long_mask = long_mask.fillna(False).astype(bool)
        else:
            long_mask = pd.Series(False, index=dataframe.index, dtype=bool)

        long_mask &= base_mask

        cooldown = max(1, int(self.buy_qbs_signal_cooldown_bars.value))
        long_recent = long_mask.shift(1).rolling(cooldown, min_periods=1).max().fillna(0).astype(bool)
        long_mask &= ~long_recent

        rebalance_hours = max(1, int(self.buy_qbs_rebalance_hours.value))
        if rebalance_hours > 1:
            hours = pd.to_datetime(dataframe["date"], utc=True, errors="coerce").dt.hour
            eligible = hours.mod(rebalance_hours).eq(0).fillna(False)
            long_mask &= eligible

        dataframe.loc[long_mask, "enter_long"] = 1
        dataframe.loc[long_mask, "enter_tag"] = "qbs_long"
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
        if not tag.startswith("qbs_"):
            return True
        if side != "long":
            return False

        row = self._pair_row_at_or_before_time(pair, current_time)
        if row is None or not bool(row.get("qbs_long_selected", False)):
            return False
        if self._open_qbs_count() >= int(self.buy_qbs_max_open_longs.value):
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
        if not tag.startswith("qbs_"):
            return float(proposed_stake)

        total_slots = max(1, int(self.buy_qbs_max_open_longs.value))
        base_cap = float(self._wallet_total()) * float(self.buy_qbs_gross_cap_pct.value) / float(total_slots)

        strength = 1.0
        row = self._pair_row_at_or_before_time(pair, current_time)
        if row is not None:
            score = abs(float(row.get("qbs_score", 0.0) or 0.0))
            threshold = max(0.05, float(self.buy_qbs_min_score.value))
            strength = np.clip(
                score / threshold,
                float(self.buy_qbs_stake_floor_mult.value),
                float(self.buy_qbs_stake_ceiling_mult.value),
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
        lev = float(self.buy_qbs_leverage.value)
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
        if not tag.startswith("qbs_"):
            return self.stoploss

        desired_open_profit = float(self.sell_qbs_stoploss.value)
        key = self._qbs_trade_key(trade)
        hwm = float(self._qbs_hwm.get(key, current_profit))
        if float(current_profit) > hwm:
            hwm = float(current_profit)
        self._qbs_hwm[key] = hwm

        if bool(self.sell_qbs_scratch_enabled.value) and hwm >= float(self.sell_qbs_scratch_arm.value):
            desired_open_profit = max(desired_open_profit, float(self.sell_qbs_scratch_stop.value))
        if bool(self.sell_qbs_trail_enabled.value) and hwm >= float(self.sell_qbs_trail_arm.value):
            desired_open_profit = max(desired_open_profit, hwm - float(self.sell_qbs_trail_offset.value))

        qbs_sl = stoploss_from_open(
            float(desired_open_profit),
            float(current_profit),
            is_short=False,
            leverage=trade.leverage,
        )
        return float(qbs_sl) if qbs_sl is not None else 1.0

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
        if not tag.startswith("qbs_"):
            return None

        row = self._pair_row_at_or_before_time(pair, current_time)
        age_hours = 0.0
        try:
            age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        except Exception:
            pass

        if row is not None:
            score = float(row.get("qbs_score", np.nan))
            long_rank = float(row.get("qbs_long_rank", np.nan))
            exit_rank = float(self.sell_qbs_rank_exit.value)
            exit_score = float(self.sell_qbs_score_exit.value)

            if np.isfinite(long_rank) and long_rank > exit_rank:
                return "qbs_rank_exit"
            if np.isfinite(score) and score <= exit_score:
                return "qbs_score_exit"
            if bool(self.sell_qbs_macro_exit.value) and not bool(row.get("qbs_btc_1d_bias", True)):
                return "qbs_macro_exit"

        if current_profit >= float(self.sell_qbs_profit_target.value):
            return "qbs_tp"
        if age_hours >= float(self.sell_qbs_time_stop_hours.value):
            return "qbs_time_stop"
        return None
