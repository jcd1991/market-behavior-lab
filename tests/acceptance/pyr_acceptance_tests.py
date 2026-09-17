#!/usr/bin/env python3
"""
Lightweight acceptance tests for continuation pyramiding helpers.

Run:
  python tests/acceptance/pyr_acceptance_tests.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "user_data" / "strategies"))

from RegimeRouted import RegimeRouted  # noqa: E402


class _P:
    def __init__(self, v):
        self.value = v


class _Trade:
    def __init__(
        self,
        pair: str,
        open_date_utc: datetime,
        stake_amount: float = 100.0,
        max_stake_amount: float = 100.0,
        open_rate: float = 100.0,
        leverage: float = 1.0,
        enter_tag: str = "cbx4h_breakout",
        is_short: bool = False,
    ) -> None:
        self.pair = pair
        self.open_date_utc = open_date_utc
        self.stake_amount = stake_amount
        self.max_stake_amount = max_stake_amount
        self.open_rate = open_rate
        self.leverage = leverage
        self.enter_tag = enter_tag
        self.is_short = is_short


class _DP:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def get_analyzed_dataframe(self, pair: str, timeframe: str):
        del pair, timeframe
        return self._df.copy(), None


class _Dummy:
    timeframe = "1h"

    buy_pyr_enabled = _P(True)
    buy_pyr_max_addons = _P(3)
    buy_pyr_addon_size_pct = _P(0.35)
    buy_pyr_arm_profit = _P(0.012)
    buy_pyr_min_bars_since_entry = _P(2)
    buy_pyr_daily_max_addons_per_pair = _P(1)
    buy_pyr_sleeve_allowlist = _P("cbx,trbk,trendpb")
    buy_pyr_only_in_regimes = _P("TREND_UP")
    buy_pyr_regime_basis = _P("current_or_entry")
    buy_pyr_r_ladder_enabled = _P(True)
    buy_pyr_r_first_add = _P(0.8)
    buy_pyr_r_step = _P(0.6)
    buy_pyr_structure_confirm_enabled = _P(True)
    buy_pyr_structure_min_signals = _P(1)
    buy_pyr_breakout_buf_atr_mult = _P(0.10)
    buy_pyr_adx_min = _P(18.0)
    buy_pyr_adx_rise_min = _P(0.5)
    buy_pyr_bbw_lookback = _P(20)
    buy_pyr_bbw_expand_ratio_min = _P(1.05)
    buy_pyr_bbw_compress_ratio_max = _P(1.10)
    buy_pyr_stx_risk_buffer_atr_mult = _P(0.10)
    sell_pyr_ratchet_enabled = _P(True)
    sell_pyr_ratchet_be_buffer = _P(0.001)
    sell_pyr_ratchet_r_mult = _P(0.5)
    buy_pyr_debug = _P(False)
    buy_sl_atr_mult = _P(2.0)

    _tokens = RegimeRouted._tokens
    _pyr_init_state = RegimeRouted._pyr_init_state
    _pyr_block = RegimeRouted._pyr_block
    _is_pyr_addon_entry_tag = RegimeRouted._is_pyr_addon_entry_tag
    _pyr_pick_num = staticmethod(RegimeRouted._pyr_pick_num)
    _pyr_trade_tag_allows = RegimeRouted._pyr_trade_tag_allows
    _pyr_daily_key = RegimeRouted._pyr_daily_key
    _pyr_stop_pct_for_trade = RegimeRouted._pyr_stop_pct_for_trade
    _pyr_structure_allows = RegimeRouted._pyr_structure_allows
    _pyr_regime_allows = RegimeRouted._pyr_regime_allows
    _pyr_bar_slot = RegimeRouted._pyr_bar_slot
    _pyr_addon_allowed = RegimeRouted._pyr_addon_allowed
    _pyr_maybe_add_position = RegimeRouted._pyr_maybe_add_position

    def __init__(self, now: datetime) -> None:
        self._pyr_addons_by_pair = {}
        self._pyr_entry_time_by_pair = {}
        self._pyr_last_add_bar_by_pair = {}
        self._pyr_daily_adds_by_pair_day = {}
        self._pyr_last_stop_pct_by_trade = {}
        self._pyr_stop_floor_open_by_trade = {}
        self._pyr_block_counts = {}
        self._pyr_add_count = 0
        self._trade_regime_state = {}

        dates = [now - timedelta(hours=3), now - timedelta(hours=2), now - timedelta(hours=1), now]
        self.dp = _DP(
            pd.DataFrame(
                {
                    "date": dates,
                    "close": [100.0, 101.0, 102.0, 103.0],
                    "atr14": [1.0, 1.0, 1.0, 1.0],
                    "cbx_donch_high": [100.5, 101.2, 101.6, 102.0],
                    "cbx_breakout_thr": [100.6, 101.3, 101.8, 102.1],
                    "cbx_adx": [18.0, 20.0, 22.0, 24.0],
                    "cbx_bbw": [0.025, 0.022, 0.020, 0.024],
                    "cbx_stx": ["up", "up", "up", "up"],
                    "cbx4h_stx_4h": ["up", "up", "up", "up"],
                    "htf_uptrend_4h": [1, 1, 1, 1],
                    "trendpb_ema_fast": [99.0, 99.5, 100.0, 101.0],
                    "composite_regime": [
                        "TREND_UP,VOL_EXP",
                        "TREND_UP,VOL_EXP",
                        "TREND_UP,VOL_EXP",
                        "TREND_UP,VOL_EXP",
                    ],
                }
            )
        )

    @staticmethod
    def _timeframe_to_minutes(tf: str) -> int:
        return 60 if tf == "1h" else 240

    @staticmethod
    def _tag_bucket(entry_tag: str | None) -> str:
        tag = str(entry_tag or "").lower()
        if "cbx" in tag:
            return "cbx"
        if "trend_pullback" in tag or "trendpb" in tag:
            return "trendpb"
        if "trbk" in tag:
            return "trbk"
        if "veb" in tag or "volex" in tag:
            return "veb"
        return "other"

    @staticmethod
    def _pair_row_at_or_before_time(pair: str, when: datetime | None) -> pd.Series | None:
        del pair, when
        return pd.Series({"composite_regime": "TREND_UP,VOL_EXP"})

    @staticmethod
    def _trade_id(trade: _Trade) -> int | None:
        return id(trade)

    @staticmethod
    def _effective_stop_pct_for_trade(pair: str, trade: _Trade) -> float:
        del pair, trade
        return 0.02


def run_tests() -> None:
    now = datetime(2025, 10, 10, 12, 0, tzinfo=timezone.utc)
    trade = _Trade(pair="ETH/USDT:USDT", open_date_utc=now - timedelta(hours=3), leverage=1.0)
    d = _Dummy(now=now)
    d._trade_regime_state[d._trade_id(trade)] = "TREND_UP"

    # Regime tokenization + allowlist
    assert d._tokens("TREND_UP, VOL_EXP") == {"TREND_UP", "VOL_EXP"}
    assert d._pyr_regime_allows("TREND_UP,VOL_EXP")
    assert not d._pyr_regime_allows("CHOP,DOWN")

    # Add-on gating allows properly armed winners after min bars
    bar_slot = d._pyr_bar_slot(now)
    rows, _ = d.dp.get_analyzed_dataframe(trade.pair, d.timeframe)
    row = rows.iloc[-1]
    prev_row = rows.iloc[-2]
    stop_pct = d._pyr_stop_pct_for_trade(trade.pair, trade, row=row)

    ok, reason = d._pyr_addon_allowed(
        pair=trade.pair,
        trade=trade,
        current_time=now,
        composite_regime="TREND_UP,VOL_EXP",
        current_profit=0.02,
        current_bar_slot=bar_slot,
        row=row,
        prev_row=prev_row,
        hist=rows,
        stop_pct=stop_pct,
    )
    assert ok and reason == "pyr_ok", (ok, reason)

    # Add-on blocked when not armed (R-ladder + arm threshold)
    ok2, reason2 = d._pyr_addon_allowed(
        pair=trade.pair,
        trade=trade,
        current_time=now,
        composite_regime="TREND_UP,VOL_EXP",
        current_profit=0.005,
        current_bar_slot=bar_slot,
        row=row,
        prev_row=prev_row,
        hist=rows,
        stop_pct=stop_pct,
    )
    assert (not ok2) and reason2 == "pyr_not_armed", (ok2, reason2)

    # Position add fires once with expected stake size and ratchet floor set
    add1 = d._pyr_maybe_add_position(
        trade=trade,
        current_time=now,
        current_rate=2000.0,
        current_profit=0.03,
        min_stake=10.0,
        max_stake=10_000.0,
    )
    assert isinstance(add1, tuple) and len(add1) == 2, add1
    add1_amt, add1_reason = add1
    assert abs(float(add1_amt) - 35.0) < 1e-9, add1
    assert add1_reason == "pyr_addon", add1
    tid = d._trade_id(trade)
    assert tid in d._pyr_stop_floor_open_by_trade
    assert float(d._pyr_stop_floor_open_by_trade[tid]) > 0.0

    # Later retry same day blocked by per-pair daily add cap
    add2 = d._pyr_maybe_add_position(
        trade=trade,
        current_time=now + timedelta(hours=3),
        current_rate=2010.0,
        current_profit=0.05,
        min_stake=10.0,
        max_stake=10_000.0,
    )
    assert add2 is None
    dkey = d._pyr_daily_key(trade.pair, now)
    assert int(d._pyr_daily_adds_by_pair_day.get(dkey, 0)) == 1

    print("pyr acceptance tests: PASS")


if __name__ == "__main__":
    run_tests()
