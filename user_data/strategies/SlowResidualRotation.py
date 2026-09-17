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

_TREND_CORE3_PAIRS = {
    "TRX/USDT:USDT",
    "DOT/USDT:USDT",
    "ATOM/USDT:USDT",
}

_TREND_DA2_PAIRS = {
    "DOT/USDT:USDT",
    "ATOM/USDT:USDT",
}


class SlowResidualRotation(IStrategy):
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

    buy_srr_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_srr_universe_profile = CategoricalParameter(
        ["full", "liquid_alts", "majors", "trend_core4", "trend_core3", "trend_da2"],
        default="liquid_alts",
        space="buy",
        optimize=False,
        load=True,
    )
    buy_srr_rebalance_hours = IntParameter(4, 24, default=12, space="buy", optimize=False, load=True)
    buy_srr_signal_cooldown_bars = IntParameter(1, 8, default=3, space="buy", optimize=False, load=True)
    buy_srr_long_topn = IntParameter(1, 4, default=2, space="buy", optimize=True, load=True)
    buy_srr_max_open_longs = IntParameter(1, 4, default=2, space="buy", optimize=False, load=True)
    buy_srr_fast_lookback = IntParameter(6, 24, default=12, space="buy", optimize=False, load=True)
    buy_srr_slow_lookback = IntParameter(18, 90, default=36, space="buy", optimize=False, load=True)
    buy_srr_breakout_lookback = IntParameter(4, 24, default=10, space="buy", optimize=False, load=True)
    buy_srr_breakout_min = DecimalParameter(0.000, 0.030, default=0.000, decimals=3, space="buy", optimize=True, load=True)
    buy_srr_breakout_body_min = DecimalParameter(0.00, 0.70, default=0.00, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_breakout_relvol_min = DecimalParameter(0.70, 2.20, default=0.85, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_rank_persistence_bars = IntParameter(1, 6, default=2, space="buy", optimize=True, load=True)
    buy_srr_relvol_len = IntParameter(6, 48, default=18, space="buy", optimize=False, load=True)
    buy_srr_relvol_min = DecimalParameter(0.70, 2.00, default=0.95, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_atr_pct_max = DecimalParameter(0.015, 0.20, default=0.090, decimals=3, space="buy", optimize=True, load=True)
    buy_srr_eth_lead_min = DecimalParameter(0.000, 0.060, default=0.006, decimals=3, space="buy", optimize=True, load=True)
    buy_srr_min_score = DecimalParameter(0.05, 0.80, default=0.18, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_entry_score_buffer = DecimalParameter(0.00, 0.10, default=0.00, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_w_fast = DecimalParameter(0.0, 1.0, default=0.35, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_w_slow = DecimalParameter(0.0, 1.0, default=0.50, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_w_breakout = DecimalParameter(0.0, 1.0, default=0.15, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_w_trend = DecimalParameter(0.0, 1.0, default=0.00, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_require_pair_4h_bias = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_srr_require_pair_1d_bias = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_srr_require_btc_1d_bias = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_srr_require_eth_lead = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_srr_ema_fast = IntParameter(12, 72, default=36, space="buy", optimize=False, load=True)
    buy_srr_ema_slow = IntParameter(24, 200, default=108, space="buy", optimize=False, load=True)
    buy_srr_ema1d_fast = IntParameter(10, 80, default=30, space="buy", optimize=False, load=True)
    buy_srr_ema1d_slow = IntParameter(30, 250, default=90, space="buy", optimize=False, load=True)
    buy_srr_gross_cap_pct = DecimalParameter(0.05, 0.60, default=0.28, decimals=2, space="buy", optimize=False, load=True)
    buy_srr_stake_floor_mult = DecimalParameter(0.50, 1.00, default=0.80, decimals=2, space="buy", optimize=False, load=True)
    buy_srr_stake_ceiling_mult = DecimalParameter(1.00, 1.80, default=1.30, decimals=2, space="buy", optimize=False, load=True)
    buy_srr_leverage = DecimalParameter(1.0, 3.0, default=1.0, decimals=1, space="buy", optimize=False, load=True)
    buy_srr_carry_enabled = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_srr_carry_w_basis = DecimalParameter(0.0, 1.0, default=0.12, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_carry_w_funding = DecimalParameter(0.0, 1.0, default=0.08, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_carry_gate_enabled = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_srr_basis_min = DecimalParameter(-0.010, 0.010, default=-0.010, decimals=4, space="buy", optimize=True, load=True)
    buy_srr_funding_min = DecimalParameter(-0.0010, 0.0010, default=-0.0010, decimals=4, space="buy", optimize=True, load=True)
    buy_srr_tsmom_gate_enabled = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_srr_tsmom_lookback_1d = IntParameter(5, 90, default=20, space="buy", optimize=True, load=True)
    buy_srr_tsmom_min_1d = DecimalParameter(-0.20, 0.20, default=-0.20, decimals=3, space="buy", optimize=True, load=True)
    buy_srr_risk_parity_enabled = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_srr_risk_target_atr_pct = DecimalParameter(0.010, 0.100, default=0.040, decimals=3, space="buy", optimize=True, load=True)
    buy_srr_risk_floor_mult = DecimalParameter(0.30, 1.20, default=0.70, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_risk_ceiling_mult = DecimalParameter(1.00, 3.00, default=1.60, decimals=2, space="buy", optimize=True, load=True)
    buy_srr_debug = BooleanParameter(default=False, space="buy", optimize=False, load=True)

    sell_srr_stoploss = DecimalParameter(-0.12, -0.01, default=-0.045, decimals=3, space="sell", optimize=True, load=True)
    sell_srr_profit_target = DecimalParameter(0.01, 0.20, default=0.070, decimals=3, space="sell", optimize=True, load=True)
    sell_srr_time_stop_hours = IntParameter(24, 240, default=120, space="sell", optimize=True, load=True)
    sell_srr_model_exit_min_hours = IntParameter(0, 72, default=0, space="sell", optimize=True, load=True)
    sell_srr_rank_exit = IntParameter(2, 12, default=5, space="sell", optimize=True, load=True)
    sell_srr_score_exit = DecimalParameter(-0.10, 0.20, default=0.02, decimals=2, space="sell", optimize=True, load=True)
    sell_srr_macro_exit = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_srr_scratch_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_srr_scratch_arm = DecimalParameter(0.005, 0.06, default=0.020, decimals=3, space="sell", optimize=True, load=True)
    sell_srr_scratch_stop = DecimalParameter(-0.010, 0.02, default=0.002, decimals=3, space="sell", optimize=True, load=True)
    sell_srr_trail_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_srr_trail_arm = DecimalParameter(0.010, 0.12, default=0.040, decimals=3, space="sell", optimize=True, load=True)
    sell_srr_trail_offset = DecimalParameter(0.004, 0.08, default=0.018, decimals=3, space="sell", optimize=True, load=True)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._srr_pair_cache: dict[str, pd.DataFrame] = {}
        self._srr_cache_signature: tuple[Any, ...] | None = None
        self._srr_hwm: dict[str, float] = {}

    def informative_pairs(self):
        if not bool(self.buy_srr_enabled.value):
            return []
        result: list[tuple[str, str] | tuple[str, str, str]] = []
        pairset = set(self._srr_pairs()) | {_REF_BTC, _REF_ETH}
        for pair in sorted(pairset):
            result.append((pair, "1d"))
            result.append((pair, self.timeframe, "mark"))
            result.append((pair, self.timeframe, "index"))
            result.append((pair, "1h", "funding_rate"))
        return result

    def _srr_pairs(self) -> list[str]:
        try:
            pairs = list(self.dp.current_whitelist() or [])
        except Exception:
            pairs = list(self.config.get("exchange", {}).get("pair_whitelist", []))
        profile = str(self.buy_srr_universe_profile.value or "liquid_alts")
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
            if profile == "trend_core3" and pair not in _TREND_CORE3_PAIRS:
                continue
            if profile == "trend_da2" and pair not in _TREND_DA2_PAIRS:
                continue
            out.append(pair)
        return out

    def _srr_signature(self) -> tuple[Any, ...]:
        return (
            tuple(sorted(self._srr_pairs())),
            int(self.buy_srr_fast_lookback.value),
            int(self.buy_srr_slow_lookback.value),
            int(self.buy_srr_breakout_lookback.value),
            float(self.buy_srr_breakout_min.value),
            float(self.buy_srr_breakout_body_min.value),
            float(self.buy_srr_breakout_relvol_min.value),
            int(self.buy_srr_rank_persistence_bars.value),
            int(self.buy_srr_relvol_len.value),
            int(self.buy_srr_rebalance_hours.value),
            int(self.buy_srr_signal_cooldown_bars.value),
            int(self.buy_srr_ema_fast.value),
            int(self.buy_srr_ema_slow.value),
            int(self.buy_srr_ema1d_fast.value),
            int(self.buy_srr_ema1d_slow.value),
            float(self.buy_srr_relvol_min.value),
            float(self.buy_srr_atr_pct_max.value),
            float(self.buy_srr_eth_lead_min.value),
            float(self.buy_srr_min_score.value),
            float(self.buy_srr_entry_score_buffer.value),
            float(self.buy_srr_w_fast.value),
            float(self.buy_srr_w_slow.value),
            float(self.buy_srr_w_breakout.value),
            float(self.buy_srr_w_trend.value),
            float(self.buy_srr_carry_w_basis.value),
            float(self.buy_srr_carry_w_funding.value),
            bool(self.buy_srr_carry_gate_enabled.value),
            float(self.buy_srr_basis_min.value),
            float(self.buy_srr_funding_min.value),
            bool(self.buy_srr_tsmom_gate_enabled.value),
            int(self.buy_srr_tsmom_lookback_1d.value),
            float(self.buy_srr_tsmom_min_1d.value),
            bool(self.buy_srr_risk_parity_enabled.value),
            float(self.buy_srr_risk_target_atr_pct.value),
            float(self.buy_srr_risk_floor_mult.value),
            float(self.buy_srr_risk_ceiling_mult.value),
            int(self.buy_srr_long_topn.value),
            bool(self.buy_srr_require_pair_4h_bias.value),
            bool(self.buy_srr_require_pair_1d_bias.value),
            bool(self.buy_srr_require_btc_1d_bias.value),
            bool(self.buy_srr_require_eth_lead.value),
            bool(self.buy_srr_carry_enabled.value),
        )

    def _default_frame(self, dataframe: DataFrame) -> DataFrame:
        defaults = {
            "srr_base_score": np.nan,
            "srr_carry_score": np.nan,
            "srr_score": np.nan,
            "srr_fast_rank": np.nan,
            "srr_slow_rank": np.nan,
            "srr_breakout_rank": np.nan,
            "srr_trend_rank": np.nan,
            "srr_long_rank": np.nan,
            "srr_breakout_raw": np.nan,
            "srr_breakout_body": np.nan,
            "srr_relvol": np.nan,
            "srr_atr_pct": np.nan,
            "srr_basis": np.nan,
            "srr_funding": np.nan,
            "srr_eth_lead": np.nan,
            "srr_tsmom_1d": np.nan,
            "srr_pair_1d_bias": False,
            "srr_btc_1d_bias": False,
            "srr_breakout_ok": False,
            "srr_long_selected": False,
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

    def _srr_trade_key(self, trade: Trade) -> str:
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
        if not bool(self.buy_srr_enabled.value):
            self._srr_pair_cache = {}
            self._srr_cache_signature = self._srr_signature()
            return

        signature = self._srr_signature()
        if self._srr_cache_signature == signature and self._srr_pair_cache:
            return

        pairs = self._srr_pairs()
        if len(pairs) < 2:
            self._srr_pair_cache = {}
            self._srr_cache_signature = signature
            return

        btc_df = self._price_frame(_REF_BTC, self.timeframe)
        eth_df = self._price_frame(_REF_ETH, self.timeframe)
        btc_1d_df = self._price_frame(_REF_BTC, "1d")
        if btc_df is None or eth_df is None or btc_1d_df is None:
            self._srr_pair_cache = {}
            self._srr_cache_signature = signature
            return

        fast_lb = max(2, int(self.buy_srr_fast_lookback.value))
        slow_lb = max(fast_lb + 2, int(self.buy_srr_slow_lookback.value))
        breakout_lb = max(2, int(self.buy_srr_breakout_lookback.value))
        relvol_len = max(4, int(self.buy_srr_relvol_len.value))
        ema_fast_len = max(4, int(self.buy_srr_ema_fast.value))
        ema_slow_len = max(ema_fast_len + 1, int(self.buy_srr_ema_slow.value))
        ema1d_fast_len = max(4, int(self.buy_srr_ema1d_fast.value))
        ema1d_slow_len = max(ema1d_fast_len + 1, int(self.buy_srr_ema1d_slow.value))
        tsmom_lb_1d = max(2, int(self.buy_srr_tsmom_lookback_1d.value))

        btc_close = pd.to_numeric(btc_df.get("close"), errors="coerce")
        eth_close = pd.to_numeric(eth_df.get("close"), errors="coerce")
        btc_fast = pd.Series(btc_close.pct_change(fast_lb).to_numpy(), index=btc_df["__date"])
        eth_fast = pd.Series(eth_close.pct_change(fast_lb).to_numpy(), index=eth_df["__date"])
        btc_slow = pd.Series(btc_close.pct_change(slow_lb).to_numpy(), index=btc_df["__date"])
        eth_slow = pd.Series(eth_close.pct_change(slow_lb).to_numpy(), index=eth_df["__date"])
        btc_ema1d_fast = ta.EMA(btc_1d_df, timeperiod=ema1d_fast_len)
        btc_ema1d_slow = ta.EMA(btc_1d_df, timeperiod=ema1d_slow_len)
        btc_1d_close = pd.to_numeric(btc_1d_df.get("close"), errors="coerce")
        eth_1d_df = self._price_frame(_REF_ETH, "1d")
        eth_1d_close = pd.to_numeric(eth_1d_df.get("close"), errors="coerce") if eth_1d_df is not None else None
        btc_1d_bias = pd.Series(
            ((btc_1d_close > pd.to_numeric(btc_ema1d_fast, errors="coerce"))
             & (pd.to_numeric(btc_ema1d_fast, errors="coerce") > pd.to_numeric(btc_ema1d_slow, errors="coerce"))).to_numpy(),
            index=btc_1d_df["__date"],
        )
        btc_tsmom_1d = btc_1d_close.pct_change(tsmom_lb_1d)
        if eth_1d_df is not None and eth_1d_close is not None:
            eth_tsmom_1d = eth_1d_close.pct_change(tsmom_lb_1d)
            market_tsmom_1d = (btc_tsmom_1d + eth_tsmom_1d.reindex_like(btc_tsmom_1d)) / 2.0
        else:
            market_tsmom_1d = btc_tsmom_1d
        market_tsmom_df = btc_1d_df[["__date"]].copy()
        market_tsmom_df["__market_tsmom_1d"] = pd.to_numeric(market_tsmom_1d, errors="coerce")

        pair_frames: dict[str, pd.DataFrame] = {}
        for pair in pairs:
            base_df = self._price_frame(pair, self.timeframe)
            daily_df = self._price_frame(pair, "1d")
            if base_df is None or daily_df is None:
                continue

            close = pd.to_numeric(base_df.get("close"), errors="coerce")
            open_ = pd.to_numeric(base_df.get("open"), errors="coerce")
            high = pd.to_numeric(base_df.get("high"), errors="coerce")
            low = pd.to_numeric(base_df.get("low"), errors="coerce")
            volume = pd.to_numeric(base_df.get("volume"), errors="coerce")
            atr_pct = ta.ATR(base_df, timeperiod=14) / close.replace(0.0, np.nan)
            relvol = volume / volume.rolling(relvol_len, min_periods=max(3, relvol_len // 3)).mean().replace(0.0, np.nan)
            ema_fast = ta.EMA(base_df, timeperiod=ema_fast_len)
            ema_slow = ta.EMA(base_df, timeperiod=ema_slow_len)
            pair_fast = close.pct_change(fast_lb)
            pair_slow = close.pct_change(slow_lb)

            idx = base_df["__date"]
            bench_fast = (btc_fast.reindex(idx).ffill() + eth_fast.reindex(idx).ffill()) / 2.0
            bench_slow = (btc_slow.reindex(idx).ffill() + eth_slow.reindex(idx).ffill()) / 2.0
            excess_fast = pd.Series(pair_fast.to_numpy(), index=idx) - bench_fast
            excess_slow = pd.Series(pair_slow.to_numpy(), index=idx) - bench_slow
            breakout_ref = high.rolling(breakout_lb).max().shift(1)
            breakout_raw = ((close / breakout_ref.replace(0.0, np.nan)) - 1.0).replace([np.inf, -np.inf], np.nan)
            bar_range = (high - low).replace(0.0, np.nan)
            breakout_body = ((close - open_) / bar_range).replace([np.inf, -np.inf], np.nan)
            breakout_ok = (breakout_raw >= float(self.buy_srr_breakout_min.value)).fillna(False)
            breakout_body_ok = (breakout_body >= float(self.buy_srr_breakout_body_min.value)).fillna(False)
            breakout_relvol_ok = (relvol >= float(self.buy_srr_breakout_relvol_min.value)).fillna(False)
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
            market_tsmom = self._merge_asof_numeric_series(base_df, market_tsmom_df, "__market_tsmom_1d")

            pair_frames[pair] = pd.DataFrame(
                {
                    "srr_excess_fast": excess_fast,
                    "srr_excess_slow": excess_slow,
                    "srr_breakout_raw": pd.Series(breakout_raw.to_numpy(), index=idx),
                    "srr_breakout_body": pd.Series(breakout_body.to_numpy(), index=idx),
                    "srr_breakout_ok": (
                        pd.Series(breakout_ok.to_numpy(), index=idx).astype(bool)
                        & pd.Series(breakout_body_ok.to_numpy(), index=idx).astype(bool)
                        & pd.Series(breakout_relvol_ok.to_numpy(), index=idx).astype(bool)
                    ),
                    "srr_eth_lead": eth_lead,
                    "srr_basis": -basis,
                    "srr_funding": -funding,
                    "srr_relvol": pd.Series(relvol.to_numpy(), index=idx),
                    "srr_atr_pct": pd.Series(atr_pct.to_numpy(), index=idx),
                    "srr_close": pd.Series(close.to_numpy(), index=idx),
                    "srr_ema_fast": pd.Series(pd.to_numeric(ema_fast, errors="coerce").to_numpy(), index=idx),
                    "srr_ema_slow": pd.Series(pd.to_numeric(ema_slow, errors="coerce").to_numpy(), index=idx),
                    "srr_pair_1d_bias": pd.Series(pair_1d_bias.to_numpy(), index=idx).astype(bool),
                    "srr_btc_1d_bias": pd.Series(btc_bias_m.to_numpy(), index=idx).astype(bool),
                    "srr_tsmom_1d": pd.Series(market_tsmom.to_numpy(), index=idx),
                }
            ).sort_index()

        if len(pair_frames) < 2:
            self._srr_pair_cache = {}
            self._srr_cache_signature = signature
            return

        fast_mat = pd.DataFrame({pair: frame["srr_excess_fast"] for pair, frame in pair_frames.items()}).sort_index()
        slow_mat = pd.DataFrame({pair: frame["srr_excess_slow"] for pair, frame in pair_frames.items()}).sort_index()
        breakout_mat = pd.DataFrame({pair: frame["srr_breakout_raw"] for pair, frame in pair_frames.items()}).sort_index()
        basis_mat = pd.DataFrame({pair: frame["srr_basis"] for pair, frame in pair_frames.items()}).sort_index()
        funding_mat = pd.DataFrame({pair: frame["srr_funding"] for pair, frame in pair_frames.items()}).sort_index()
        relvol_mat = pd.DataFrame({pair: frame["srr_relvol"] for pair, frame in pair_frames.items()}).sort_index()
        atr_mat = pd.DataFrame({pair: frame["srr_atr_pct"] for pair, frame in pair_frames.items()}).sort_index()
        close_mat = pd.DataFrame({pair: frame["srr_close"] for pair, frame in pair_frames.items()}).sort_index()
        ema_fast_mat = pd.DataFrame({pair: frame["srr_ema_fast"] for pair, frame in pair_frames.items()}).sort_index()
        ema_slow_mat = pd.DataFrame({pair: frame["srr_ema_slow"] for pair, frame in pair_frames.items()}).sort_index()
        trend_mat = ((close_mat / ema_slow_mat.replace(0.0, np.nan)) - 1.0).clip(lower=-0.20, upper=0.20)
        breakout_ok_mat = pd.DataFrame({pair: frame["srr_breakout_ok"] for pair, frame in pair_frames.items()}).sort_index()
        pair_1d_bias_mat = pd.DataFrame({pair: frame["srr_pair_1d_bias"] for pair, frame in pair_frames.items()}).sort_index()
        btc_1d_bias_mat = pd.DataFrame({pair: frame["srr_btc_1d_bias"] for pair, frame in pair_frames.items()}).sort_index()
        tsmom_mat = pd.DataFrame({pair: frame["srr_tsmom_1d"] for pair, frame in pair_frames.items()}).sort_index()
        eth_lead_mat = pd.DataFrame({pair: frame["srr_eth_lead"] for pair, frame in pair_frames.items()}).sort_index()

        rank_fast = self._centered_rank_frame(fast_mat).fillna(0.0)
        rank_slow = self._centered_rank_frame(slow_mat).fillna(0.0)
        rank_breakout = self._centered_rank_frame(breakout_mat.clip(lower=-0.20, upper=0.20)).fillna(0.0)
        rank_trend = self._centered_rank_frame(trend_mat).fillna(0.0)
        rank_basis = self._centered_rank_frame(basis_mat).fillna(0.0)
        rank_funding = self._centered_rank_frame(funding_mat).fillna(0.0)

        base_weights = {
            "fast": float(self.buy_srr_w_fast.value),
            "slow": float(self.buy_srr_w_slow.value),
            "breakout": float(self.buy_srr_w_breakout.value),
            "trend": float(self.buy_srr_w_trend.value),
        }
        base_wsum = sum(abs(v) for v in base_weights.values()) or 1.0
        base_score = (
            rank_fast * base_weights["fast"]
            + rank_slow * base_weights["slow"]
            + rank_breakout * base_weights["breakout"]
            + rank_trend * base_weights["trend"]
        ) / base_wsum

        carry_weights = {
            "basis": float(self.buy_srr_carry_w_basis.value),
            "funding": float(self.buy_srr_carry_w_funding.value),
        }
        carry_wsum = sum(abs(v) for v in carry_weights.values()) or 1.0
        carry_score = (
            rank_basis * carry_weights["basis"]
            + rank_funding * carry_weights["funding"]
        ) / carry_wsum

        if bool(self.buy_srr_carry_enabled.value):
            score = base_score + carry_score
        else:
            score = base_score

        long_rank = score.rank(axis=1, ascending=False, method="min")
        topn = int(self.buy_srr_long_topn.value)
        long_selected = (long_rank <= topn) & (score >= float(self.buy_srr_min_score.value))

        relvol_ok = relvol_mat >= float(self.buy_srr_relvol_min.value)
        atr_ok = atr_mat <= float(self.buy_srr_atr_pct_max.value)
        long_selected &= relvol_ok.fillna(False) & atr_ok.fillna(False)

        if bool(self.buy_srr_require_pair_4h_bias.value):
            long_selected &= ((close_mat > ema_fast_mat) & (ema_fast_mat > ema_slow_mat)).fillna(False)
        if bool(self.buy_srr_require_pair_1d_bias.value):
            long_selected &= pair_1d_bias_mat.fillna(False)
        if bool(self.buy_srr_require_btc_1d_bias.value):
            long_selected &= btc_1d_bias_mat.fillna(False)
        if bool(self.buy_srr_require_eth_lead.value):
            long_selected &= (eth_lead_mat >= float(self.buy_srr_eth_lead_min.value)).fillna(False)

        if bool(self.buy_srr_carry_gate_enabled.value):
            long_selected &= (basis_mat >= float(self.buy_srr_basis_min.value)).fillna(False)
            long_selected &= (funding_mat >= float(self.buy_srr_funding_min.value)).fillna(False)

        if bool(self.buy_srr_tsmom_gate_enabled.value):
            long_selected &= (tsmom_mat >= float(self.buy_srr_tsmom_min_1d.value)).fillna(False)

        long_selected &= breakout_ok_mat.fillna(False)

        persistence = max(1, int(self.buy_srr_rank_persistence_bars.value))
        if persistence > 1:
            persist_ok = (long_rank <= (topn + 1)).rolling(persistence, min_periods=persistence).sum() >= persistence
            long_selected &= persist_ok.fillna(False)

        cache: dict[str, pd.DataFrame] = {}
        for pair in pair_frames:
            cache[pair] = pd.DataFrame(
                {
                    "date": score.index,
                    "srr_base_score": pd.to_numeric(base_score[pair], errors="coerce").values,
                    "srr_carry_score": pd.to_numeric(carry_score[pair], errors="coerce").values,
                    "srr_score": pd.to_numeric(score[pair], errors="coerce").values,
                    "srr_fast_rank": pd.to_numeric(rank_fast[pair], errors="coerce").values,
                    "srr_slow_rank": pd.to_numeric(rank_slow[pair], errors="coerce").values,
                    "srr_breakout_rank": pd.to_numeric(rank_breakout[pair], errors="coerce").values,
                    "srr_trend_rank": pd.to_numeric(rank_trend[pair], errors="coerce").values,
                    "srr_long_rank": pd.to_numeric(long_rank[pair], errors="coerce").values,
                    "srr_breakout_raw": pd.to_numeric(breakout_mat[pair], errors="coerce").values,
                    "srr_breakout_body": pd.to_numeric(pair_frames[pair]["srr_breakout_body"], errors="coerce").values,
                    "srr_relvol": pd.to_numeric(relvol_mat[pair], errors="coerce").values,
                    "srr_atr_pct": pd.to_numeric(atr_mat[pair], errors="coerce").values,
                    "srr_basis": pd.to_numeric((-basis_mat[pair]), errors="coerce").values,
                    "srr_funding": pd.to_numeric((-funding_mat[pair]), errors="coerce").values,
                    "srr_eth_lead": pd.to_numeric(eth_lead_mat[pair], errors="coerce").values,
                    "srr_tsmom_1d": pd.to_numeric(tsmom_mat[pair], errors="coerce").values,
                    "srr_pair_1d_bias": pair_1d_bias_mat[pair].fillna(False).astype(bool).values,
                    "srr_btc_1d_bias": btc_1d_bias_mat[pair].fillna(False).astype(bool).values,
                    "srr_breakout_ok": breakout_ok_mat[pair].fillna(False).astype(bool).values,
                    "srr_long_selected": long_selected[pair].fillna(False).astype(bool).values,
                }
            ).dropna(subset=["date"]).sort_values("date")

        self._srr_pair_cache = cache
        self._srr_cache_signature = signature

    def _merge_pair_cache(self, dataframe: DataFrame, pair: str) -> DataFrame:
        self._build_score_cache()
        cached = self._srr_pair_cache.get(pair)
        if cached is None or cached.empty:
            return self._default_frame(dataframe.copy())

        left = dataframe.copy()
        left["__srr_date"] = pd.to_datetime(left["date"], utc=True, errors="coerce")
        left = left.sort_values("__srr_date")
        right = cached.copy().rename(columns={"date": "__srr_date"}).sort_values("__srr_date")
        merged = pd.merge_asof(left, right, on="__srr_date", direction="backward")
        merged = merged.sort_index()
        merged.drop(columns=["__srr_date"], inplace=True, errors="ignore")
        for col in ("srr_pair_1d_bias", "srr_btc_1d_bias", "srr_breakout_ok", "srr_long_selected"):
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

    def _open_srr_count(self) -> int:
        count = 0
        for trade in self._safe_get_open_trades():
            tag = str(getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or "")
            if tag.startswith("srr_") and not bool(getattr(trade, "is_short", False)):
                count += 1
        return count

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not bool(self.buy_srr_enabled.value):
            return self._default_frame(dataframe.copy())
        return self._merge_pair_cache(dataframe, metadata["pair"])

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "enter_long"] = 0
        dataframe.loc[:, "enter_short"] = 0
        dataframe.loc[:, "enter_tag"] = ""

        if not bool(self.buy_srr_enabled.value):
            return dataframe

        base_mask = (dataframe["volume"] > 0).fillna(False)
        long_mask = dataframe.get("srr_long_selected", False)
        if isinstance(long_mask, pd.Series):
            long_mask = long_mask.fillna(False).astype(bool)
        else:
            long_mask = pd.Series(False, index=dataframe.index, dtype=bool)

        long_mask &= base_mask

        cooldown = max(1, int(self.buy_srr_signal_cooldown_bars.value))
        long_recent = long_mask.shift(1).rolling(cooldown, min_periods=1).max().fillna(0).astype(bool)
        long_mask &= ~long_recent

        rebalance_hours = max(1, int(self.buy_srr_rebalance_hours.value))
        if rebalance_hours > 1:
            hours = pd.to_datetime(dataframe["date"], utc=True, errors="coerce").dt.hour
            eligible = hours.mod(rebalance_hours).eq(0).fillna(False)
            long_mask &= eligible

        dataframe.loc[long_mask, "enter_long"] = 1
        dataframe.loc[long_mask, "enter_tag"] = "srr_long"
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
        if not tag.startswith("srr_"):
            return True
        if side != "long":
            return False

        row = self._pair_row_at_or_before_time(pair, current_time)
        if row is None or not bool(row.get("srr_long_selected", False)):
            return False
        if not bool(row.get("srr_breakout_ok", False)):
            return False
        score = float(row.get("srr_score", np.nan))
        min_score = float(self.buy_srr_min_score.value) + float(self.buy_srr_entry_score_buffer.value)
        if np.isfinite(score) and score < min_score:
            return False
        if self._open_srr_count() >= int(self.buy_srr_max_open_longs.value):
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
        if not tag.startswith("srr_"):
            return float(proposed_stake)

        total_slots = max(1, int(self.buy_srr_max_open_longs.value))
        base_cap = float(self._wallet_total()) * float(self.buy_srr_gross_cap_pct.value) / float(total_slots)

        strength = 1.0
        row = self._pair_row_at_or_before_time(pair, current_time)
        if row is not None:
            score = abs(float(row.get("srr_score", 0.0) or 0.0))
            threshold = max(0.05, float(self.buy_srr_min_score.value))
            strength = np.clip(
                score / threshold,
                float(self.buy_srr_stake_floor_mult.value),
                float(self.buy_srr_stake_ceiling_mult.value),
            )

        stake = min(float(proposed_stake), float(max_stake), float(base_cap) * float(strength))
        if bool(self.buy_srr_risk_parity_enabled.value) and row is not None:
            atr_pct = float(row.get("srr_atr_pct", np.nan))
            if np.isfinite(atr_pct) and atr_pct > 0:
                vol_mult = np.clip(
                    float(self.buy_srr_risk_target_atr_pct.value) / atr_pct,
                    float(self.buy_srr_risk_floor_mult.value),
                    float(self.buy_srr_risk_ceiling_mult.value),
                )
                stake *= float(vol_mult)
        stake = min(stake, float(max_stake))
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
        lev = float(self.buy_srr_leverage.value)
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
        if not tag.startswith("srr_"):
            return self.stoploss

        desired_open_profit = float(self.sell_srr_stoploss.value)
        key = self._srr_trade_key(trade)
        hwm = float(self._srr_hwm.get(key, current_profit))
        if float(current_profit) > hwm:
            hwm = float(current_profit)
        self._srr_hwm[key] = hwm

        if bool(self.sell_srr_scratch_enabled.value) and hwm >= float(self.sell_srr_scratch_arm.value):
            desired_open_profit = max(desired_open_profit, float(self.sell_srr_scratch_stop.value))
        if bool(self.sell_srr_trail_enabled.value) and hwm >= float(self.sell_srr_trail_arm.value):
            desired_open_profit = max(desired_open_profit, hwm - float(self.sell_srr_trail_offset.value))

        srr_sl = stoploss_from_open(
            float(desired_open_profit),
            float(current_profit),
            is_short=False,
            leverage=trade.leverage,
        )
        return float(srr_sl) if srr_sl is not None else 1.0

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
        if not tag.startswith("srr_"):
            return None

        row = self._pair_row_at_or_before_time(pair, current_time)
        age_hours = 0.0
        try:
            age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600.0
        except Exception:
            pass

        if row is not None:
            score = float(row.get("srr_score", np.nan))
            long_rank = float(row.get("srr_long_rank", np.nan))
            exit_rank = float(self.sell_srr_rank_exit.value)
            exit_score = float(self.sell_srr_score_exit.value)
            model_exit_min_hours = float(self.sell_srr_model_exit_min_hours.value)

            if age_hours >= model_exit_min_hours:
                if np.isfinite(long_rank) and long_rank > exit_rank:
                    return "srr_rank_exit"
                if np.isfinite(score) and score <= exit_score:
                    return "srr_score_exit"
            if bool(self.sell_srr_macro_exit.value) and not bool(row.get("srr_btc_1d_bias", True)):
                return "srr_macro_exit"

        if current_profit >= float(self.sell_srr_profit_target.value):
            return "srr_tp"
        if age_hours >= float(self.sell_srr_time_stop_hours.value):
            return "srr_time_stop"
        return None
