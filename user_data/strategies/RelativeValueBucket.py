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


_PAIR_LEADER_MAP: dict[str, str] = {
    "ETH/USDT:USDT": "BTC/USDT:USDT",
    "DOGE/USDT:USDT": "BTC/USDT:USDT",
    "ADA/USDT:USDT": "ETH/USDT:USDT",
    "LINK/USDT:USDT": "ETH/USDT:USDT",
    "DOT/USDT:USDT": "ETH/USDT:USDT",
    "NEAR/USDT:USDT": "ETH/USDT:USDT",
    "UNI/USDT:USDT": "ETH/USDT:USDT",
    "ATOM/USDT:USDT": "ETH/USDT:USDT",
    "FIL/USDT:USDT": "ETH/USDT:USDT",
    "LTC/USDT:USDT": "BTC/USDT:USDT",
    "ARB/USDT:USDT": "ETH/USDT:USDT",
    "OP/USDT:USDT": "ETH/USDT:USDT",
    "APT/USDT:USDT": "ETH/USDT:USDT",
    "PEPE/USDT:USDT": "DOGE/USDT:USDT",
    "TRX/USDT:USDT": "BTC/USDT:USDT",
    "ETC/USDT:USDT": "ETH/USDT:USDT",
    "AAVE/USDT:USDT": "ETH/USDT:USDT",
    "INJ/USDT:USDT": "ETH/USDT:USDT",
    "SEI/USDT:USDT": "ETH/USDT:USDT",
    "WLD/USDT:USDT": "ETH/USDT:USDT",
    "TIA/USDT:USDT": "ETH/USDT:USDT",
    "FET/USDT:USDT": "ETH/USDT:USDT",
    "RNDR/USDT:USDT": "ETH/USDT:USDT",
    "BONK/USDT:USDT": "DOGE/USDT:USDT",
    "JUP/USDT:USDT": "ETH/USDT:USDT",
}

_MEME_PAIRS = {"DOGE/USDT:USDT", "PEPE/USDT:USDT", "BONK/USDT:USDT"}
_CORE2_PAIRS = {"ETC/USDT:USDT", "LINK/USDT:USDT"}
_CORE4_PAIRS = {"ETC/USDT:USDT", "FIL/USDT:USDT", "LINK/USDT:USDT", "NEAR/USDT:USDT"}
_CORE5_PAIRS = _CORE4_PAIRS | {"ARB/USDT:USDT"}


class RelativeValueBucket(IStrategy):
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

    buy_rv_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_rv_universe_profile = CategoricalParameter(
        ["all", "no_meme", "core2", "core4", "core5"],
        default="all",
        space="buy",
        optimize=False,
        load=True,
    )
    buy_rv_side_mode = CategoricalParameter(
        ["both", "long_only", "short_only"],
        default="both",
        space="buy",
        optimize=False,
        load=True,
    )
    buy_rv_resid_lookback = IntParameter(48, 240, default=96, space="buy", optimize=False, load=True)
    buy_rv_beta_lookback = IntParameter(48, 240, default=96, space="buy", optimize=False, load=True)
    buy_rv_corr_min = DecimalParameter(0.10, 0.90, default=0.45, decimals=2, space="buy", optimize=True, load=True)
    buy_rv_beta_abs_max = DecimalParameter(0.50, 3.00, default=2.20, decimals=2, space="buy", optimize=False, load=True)
    buy_rv_z_enter = DecimalParameter(1.00, 3.50, default=2.00, decimals=2, space="buy", optimize=True, load=True)
    buy_rv_z_max = DecimalParameter(1.50, 6.00, default=4.00, decimals=2, space="buy", optimize=False, load=True)
    buy_rv_min_recover = DecimalParameter(0.00, 1.00, default=0.10, decimals=2, space="buy", optimize=True, load=True)
    buy_rv_relvol_len = IntParameter(12, 72, default=24, space="buy", optimize=False, load=True)
    buy_rv_relvol_min = DecimalParameter(0.50, 1.50, default=0.80, decimals=2, space="buy", optimize=True, load=True)
    buy_rv_adx_max = DecimalParameter(10.0, 40.0, default=22.0, decimals=1, space="buy", optimize=True, load=True)
    buy_rv_atr_pct_max = DecimalParameter(0.01, 0.15, default=0.06, decimals=3, space="buy", optimize=True, load=True)
    buy_rv_require_prev_extreme = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_rv_require_reversion_candle = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_rv_leader_trend_filter = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_rv_leader_fast = IntParameter(24, 96, default=48, space="buy", optimize=False, load=True)
    buy_rv_leader_slow = IntParameter(72, 240, default=144, space="buy", optimize=False, load=True)
    buy_rv_max_open_same_leader = IntParameter(1, 2, default=1, space="buy", optimize=False, load=True)
    buy_rv_cap_pct = DecimalParameter(0.05, 0.30, default=0.18, decimals=2, space="buy", optimize=False, load=True)
    buy_rv_leverage = DecimalParameter(1.0, 3.0, default=1.0, decimals=1, space="buy", optimize=False, load=True)

    sell_rv_stoploss = DecimalParameter(-0.08, -0.005, default=-0.025, decimals=3, space="sell", optimize=True, load=True)
    sell_rv_profit_target = DecimalParameter(0.003, 0.04, default=0.012, decimals=3, space="sell", optimize=True, load=True)
    sell_rv_time_stop_minutes = IntParameter(60, 1440, default=360, space="sell", optimize=True, load=True)
    sell_rv_mean_exit_z = DecimalParameter(0.05, 1.50, default=0.40, decimals=2, space="sell", optimize=True, load=True)
    sell_rv_mean_exit_profit_floor = DecimalParameter(-0.02, 0.01, default=-0.003, decimals=3, space="sell", optimize=True, load=True)
    sell_rv_scratch_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_rv_scratch_arm = DecimalParameter(0.002, 0.03, default=0.007, decimals=3, space="sell", optimize=True, load=True)
    sell_rv_scratch_stop = DecimalParameter(-0.005, 0.01, default=0.000, decimals=3, space="sell", optimize=True, load=True)
    sell_rv_trail_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_rv_trail_arm = DecimalParameter(0.004, 0.05, default=0.012, decimals=3, space="sell", optimize=True, load=True)
    sell_rv_trail_offset = DecimalParameter(0.001, 0.03, default=0.005, decimals=3, space="sell", optimize=True, load=True)

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._rv_hwm: dict[str, float] = {}

    def _rv_trade_key(self, trade: Trade) -> str:
        return f"{getattr(trade, 'id', 'na')}|{getattr(trade, 'pair', '')}|{getattr(trade, 'open_date_utc', '')}"

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

    def _rv_pair_allowed(self, pair: str) -> bool:
        if pair not in _PAIR_LEADER_MAP:
            return False
        profile = str(self.buy_rv_universe_profile.value or "all")
        if profile == "no_meme" and pair in _MEME_PAIRS:
            return False
        if profile == "core2" and pair not in _CORE2_PAIRS:
            return False
        if profile == "core4" and pair not in _CORE4_PAIRS:
            return False
        if profile == "core5" and pair not in _CORE5_PAIRS:
            return False
        return True

    def _rv_leader(self, pair: str) -> str | None:
        if not self._rv_pair_allowed(pair):
            return None
        return _PAIR_LEADER_MAP.get(pair)

    def _pair_row_at_or_before_time(self, pair: str, when: datetime) -> pd.Series | None:
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            return None
        if dataframe is None or dataframe.empty or "date" not in dataframe.columns:
            return None
        try:
            ts = pd.Timestamp(when, tz="UTC")
            window = dataframe.loc[pd.to_datetime(dataframe["date"], utc=True, errors="coerce") <= ts]
        except Exception:
            window = dataframe
        if window.empty:
            return None
        return window.iloc[-1]

    def _rv_open_same_leader_count(self, leader: str) -> int:
        count = 0
        for tr in self._safe_get_open_trades():
            tag = str(getattr(tr, "enter_tag", None) or getattr(tr, "entry_tag", None) or "")
            if not tag.startswith("rv_"):
                continue
            if self._rv_leader(str(getattr(tr, "pair", ""))) == leader:
                count += 1
        return count

    def _rv_defaults(self, dataframe: DataFrame) -> DataFrame:
        dataframe["rv_leader_close"] = np.nan
        dataframe["rv_corr"] = np.nan
        dataframe["rv_beta"] = np.nan
        dataframe["rv_resid_z"] = np.nan
        dataframe["rv_relvol"] = np.nan
        dataframe["rv_adx"] = np.nan
        dataframe["rv_atr_pct"] = np.nan
        dataframe["rv_signal_long"] = False
        dataframe["rv_signal_short"] = False
        return dataframe

    def _rv_add_indicators(self, dataframe: DataFrame, pair: str) -> DataFrame:
        if not bool(self.buy_rv_enabled.value) or not self._rv_pair_allowed(pair):
            return self._rv_defaults(dataframe)

        leader = self._rv_leader(pair)
        if not leader:
            return self._rv_defaults(dataframe)

        try:
            leader_df = self.dp.get_pair_dataframe(pair=leader, timeframe=self.timeframe)
        except Exception:
            leader_df = None
        if leader_df is None or leader_df.empty:
            return self._rv_defaults(dataframe)

        merged = dataframe.copy()
        left = merged.sort_values("date").copy()
        right = leader_df[["date", "close"]].copy()
        left["_rv_date"] = pd.to_datetime(left["date"], utc=True, errors="coerce")
        right["_rv_date"] = pd.to_datetime(right["date"], utc=True, errors="coerce")
        right["rv_leader_close"] = pd.to_numeric(right["close"], errors="coerce")
        right = right.drop(columns=["date", "close"]).sort_values("_rv_date")
        left = left.sort_values("_rv_date")
        merged = pd.merge_asof(left, right, on="_rv_date", direction="backward").sort_index()

        close = pd.to_numeric(merged.get("close"), errors="coerce")
        open_ = pd.to_numeric(merged.get("open"), errors="coerce")
        volume = pd.to_numeric(merged.get("volume"), errors="coerce")
        leader_close = pd.to_numeric(merged.get("rv_leader_close"), errors="coerce")
        adx = pd.to_numeric(ta.ADX(merged, timeperiod=14), errors="coerce")
        atr = pd.to_numeric(ta.ATR(merged, timeperiod=14), errors="coerce")
        atr_pct = atr / close.replace(0, np.nan)
        leader_fast = leader_close.ewm(
            span=max(2, int(self.buy_rv_leader_fast.value)),
            adjust=False,
            min_periods=max(2, int(self.buy_rv_leader_fast.value)),
        ).mean()
        leader_slow = leader_close.ewm(
            span=max(3, int(self.buy_rv_leader_slow.value)),
            adjust=False,
            min_periods=max(3, int(self.buy_rv_leader_slow.value)),
        ).mean()

        resid_lb = max(24, int(self.buy_rv_resid_lookback.value))
        beta_lb = max(24, int(self.buy_rv_beta_lookback.value))
        minp_resid = max(12, resid_lb // 3)
        minp_beta = max(12, beta_lb // 3)
        relvol_len = max(6, int(self.buy_rv_relvol_len.value))

        log_close = np.log(close.replace(0, np.nan))
        log_leader = np.log(leader_close.replace(0, np.nan))
        ret_close = log_close.diff()
        ret_leader = log_leader.diff()

        corr = ret_close.rolling(beta_lb, min_periods=minp_beta).corr(ret_leader)
        cov = log_close.rolling(beta_lb, min_periods=minp_beta).cov(log_leader)
        var_leader = log_leader.rolling(beta_lb, min_periods=minp_beta).var(ddof=0)
        beta_abs_max = float(self.buy_rv_beta_abs_max.value)
        beta = (cov / var_leader.replace(0, np.nan)).clip(lower=-beta_abs_max, upper=beta_abs_max)

        resid = log_close - (beta * log_leader)
        resid_mu = resid.rolling(resid_lb, min_periods=minp_resid).mean()
        resid_sd = resid.rolling(resid_lb, min_periods=minp_resid).std(ddof=0).replace(0, np.nan)
        resid_z = (resid - resid_mu) / resid_sd

        relvol = volume / volume.rolling(relvol_len, min_periods=max(4, relvol_len // 3)).mean().replace(0, np.nan)
        recover = resid_z - resid_z.shift(1)

        long_signal = (resid_z <= -float(self.buy_rv_z_enter.value)).fillna(False)
        long_signal &= (resid_z >= -float(self.buy_rv_z_max.value)).fillna(False)
        long_signal &= (recover >= float(self.buy_rv_min_recover.value)).fillna(False)
        long_signal &= (corr >= float(self.buy_rv_corr_min.value)).fillna(False)
        long_signal &= (relvol >= float(self.buy_rv_relvol_min.value)).fillna(False)
        long_signal &= (adx <= float(self.buy_rv_adx_max.value)).fillna(False)
        long_signal &= (atr_pct <= float(self.buy_rv_atr_pct_max.value)).fillna(False)
        long_signal &= beta.notna().fillna(False)

        short_signal = (resid_z >= float(self.buy_rv_z_enter.value)).fillna(False)
        short_signal &= (resid_z <= float(self.buy_rv_z_max.value)).fillna(False)
        short_signal &= (recover <= -float(self.buy_rv_min_recover.value)).fillna(False)
        short_signal &= (corr >= float(self.buy_rv_corr_min.value)).fillna(False)
        short_signal &= (relvol >= float(self.buy_rv_relvol_min.value)).fillna(False)
        short_signal &= (adx <= float(self.buy_rv_adx_max.value)).fillna(False)
        short_signal &= (atr_pct <= float(self.buy_rv_atr_pct_max.value)).fillna(False)
        short_signal &= beta.notna().fillna(False)

        if bool(self.buy_rv_require_prev_extreme.value):
            long_signal &= (resid_z.shift(1) <= -float(self.buy_rv_z_enter.value)).fillna(False)
            short_signal &= (resid_z.shift(1) >= float(self.buy_rv_z_enter.value)).fillna(False)

        if bool(self.buy_rv_require_reversion_candle.value):
            long_signal &= (close >= open_).fillna(False)
            short_signal &= (close <= open_).fillna(False)

        if bool(self.buy_rv_leader_trend_filter.value):
            long_signal &= (leader_fast > leader_slow).fillna(False)
            short_signal &= (leader_fast < leader_slow).fillna(False)

        side_mode = str(self.buy_rv_side_mode.value or "both")
        if side_mode == "long_only":
            short_signal = pd.Series(False, index=merged.index, dtype=bool)
        elif side_mode == "short_only":
            long_signal = pd.Series(False, index=merged.index, dtype=bool)

        merged["rv_corr"] = corr
        merged["rv_beta"] = beta
        merged["rv_resid_z"] = resid_z
        merged["rv_relvol"] = relvol
        merged["rv_adx"] = adx
        merged["rv_atr_pct"] = atr_pct
        merged["rv_signal_long"] = long_signal.fillna(False).astype(bool)
        merged["rv_signal_short"] = short_signal.fillna(False).astype(bool)
        merged.drop(columns=["_rv_date"], inplace=True, errors="ignore")
        return merged

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return self._rv_add_indicators(dataframe, metadata["pair"])

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "enter_long"] = 0
        dataframe.loc[:, "enter_short"] = 0
        dataframe.loc[:, "enter_tag"] = ""

        pair = metadata["pair"]
        if not bool(self.buy_rv_enabled.value) or not self._rv_pair_allowed(pair):
            return dataframe

        long_mask = dataframe.get("rv_signal_long", False).fillna(False).astype(bool)
        short_mask = dataframe.get("rv_signal_short", False).fillna(False).astype(bool)
        base_mask = (dataframe["volume"] > 0).fillna(False)

        long_mask &= base_mask
        short_mask &= base_mask

        conflict = long_mask & short_mask
        long_mask &= ~conflict
        short_mask &= ~conflict

        dataframe.loc[long_mask, "enter_long"] = 1
        dataframe.loc[long_mask, "enter_tag"] = "rv_long"
        dataframe.loc[short_mask, "enter_short"] = 1
        dataframe.loc[short_mask, "enter_tag"] = "rv_short"
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
        if not str(entry_tag or "").startswith("rv_"):
            return True
        leader = self._rv_leader(pair)
        if not leader:
            return False
        max_same = int(self.buy_rv_max_open_same_leader.value)
        if max_same > 0 and self._rv_open_same_leader_count(leader) >= max_same:
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
        if not str(entry_tag or "").startswith("rv_"):
            return float(proposed_stake)
        per_trade_cap = float(self._wallet_total()) * float(self.buy_rv_cap_pct.value)
        stake = min(float(proposed_stake), float(max_stake), float(per_trade_cap))
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
        lev = float(self.buy_rv_leverage.value)
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
        if not tag.startswith("rv_"):
            return self.stoploss

        desired_open_profit = float(self.sell_rv_stoploss.value)
        key = self._rv_trade_key(trade)
        hwm = float(self._rv_hwm.get(key, current_profit))
        if float(current_profit) > hwm:
            hwm = float(current_profit)
        self._rv_hwm[key] = hwm

        if bool(self.sell_rv_scratch_enabled.value) and hwm >= float(self.sell_rv_scratch_arm.value):
            desired_open_profit = max(desired_open_profit, float(self.sell_rv_scratch_stop.value))
        if bool(self.sell_rv_trail_enabled.value) and hwm >= float(self.sell_rv_trail_arm.value):
            desired_open_profit = max(desired_open_profit, hwm - float(self.sell_rv_trail_offset.value))

        rv_sl = stoploss_from_open(
            float(desired_open_profit),
            float(current_profit),
            is_short=trade.is_short,
            leverage=trade.leverage,
        )
        return float(rv_sl) if rv_sl is not None else 1.0

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
        if not tag.startswith("rv_"):
            return None

        row = self._pair_row_at_or_before_time(pair, current_time)
        age_min = 0.0
        try:
            age_min = (current_time - trade.open_date_utc).total_seconds() / 60.0
        except Exception:
            pass

        if row is not None:
            resid_z = float(row.get("rv_resid_z", np.nan))
            if np.isfinite(resid_z):
                exit_z = float(self.sell_rv_mean_exit_z.value)
                profit_floor = float(self.sell_rv_mean_exit_profit_floor.value)
                if (not trade.is_short) and resid_z >= -exit_z and float(current_profit) >= profit_floor:
                    return "rv_mean_exit"
                if trade.is_short and resid_z <= exit_z and float(current_profit) >= profit_floor:
                    return "rv_mean_exit"

        if current_profit >= float(self.sell_rv_profit_target.value):
            return "rv_tp"

        if age_min >= float(self.sell_rv_time_stop_minutes.value):
            return "rv_time_stop"

        return None
