import sys
from pathlib import Path

import numpy as np
import pandas as pd
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import (
    BooleanParameter,
    DecimalParameter,
    IntParameter,
    IStrategy,
    stoploss_from_open,
)
from pandas import DataFrame

# Ensure strategies directory is in path (required for hyperopt parallel workers)
_strategies_dir = Path(__file__).parent
if str(_strategies_dir) not in sys.path:
    sys.path.insert(0, str(_strategies_dir))

from CrossSectionalRotation_KR import _MAJORS_PAIRS, _TAIL_PAIRS
from spot_arch_utils import (
    apply_runtime_overrides,
    asset_set_from_pairs,
    base_asset,
    current_whitelist,
    resolve_pair_by_asset,
)


_TAIL_ASSETS = asset_set_from_pairs(_TAIL_PAIRS)
_MAJORS_ASSETS = asset_set_from_pairs(_MAJORS_PAIRS)


class PortfolioAllocatorSpot(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "4h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 300
    position_adjustment_enable = False
    use_custom_stoploss = True
    stoploss = -0.15
    minimal_roi = {"0": 100.0}
    _OVERRIDES_ENV = "ALLOC_SPOT_OVERRIDES"

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

    buy_pa_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_pa_liquid_only = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_pa_majors_only = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_pa_momo_fast = IntParameter(1, 12, default=3, space="buy", optimize=True, load=True)
    buy_pa_momo_mid = IntParameter(3, 24, default=9, space="buy", optimize=True, load=True)
    buy_pa_momo_slow = IntParameter(6, 48, default=21, space="buy", optimize=True, load=True)
    buy_pa_w_fast = DecimalParameter(0.0, 1.0, default=0.30, decimals=2, space="buy", optimize=True, load=True)
    buy_pa_w_mid = DecimalParameter(0.0, 1.0, default=0.35, decimals=2, space="buy", optimize=True, load=True)
    buy_pa_w_slow = DecimalParameter(0.0, 1.0, default=0.35, decimals=2, space="buy", optimize=True, load=True)
    buy_pa_relvol_len = IntParameter(4, 48, default=12, space="buy", optimize=False, load=True)
    buy_pa_relvol_min = DecimalParameter(0.50, 2.00, default=0.90, decimals=2, space="buy", optimize=True, load=True)
    buy_pa_atr_pct_max = DecimalParameter(0.01, 0.20, default=0.10, decimals=3, space="buy", optimize=True, load=True)
    buy_pa_ema_fast = IntParameter(4, 24, default=8, space="buy", optimize=False, load=True)
    buy_pa_ema_slow = IntParameter(8, 60, default=21, space="buy", optimize=False, load=True)
    buy_pa_require_trend = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_pa_require_fast_positive = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_pa_topn = IntParameter(1, 6, default=2, space="buy", optimize=True, load=True)
    buy_pa_min_score = DecimalParameter(0.05, 0.80, default=0.22, decimals=2, space="buy", optimize=True, load=True)
    buy_pa_rebalance_bars = IntParameter(1, 6, default=1, space="buy", optimize=False, load=True)
    buy_pa_btc_filter_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_pa_btc_ema_fast = IntParameter(4, 24, default=8, space="buy", optimize=False, load=True)
    buy_pa_btc_ema_slow = IntParameter(8, 60, default=21, space="buy", optimize=False, load=True)
    buy_pa_btc_momo_lb = IntParameter(1, 12, default=3, space="buy", optimize=False, load=True)
    buy_pa_btc_momo_min = DecimalParameter(-0.10, 0.10, default=0.01, decimals=2, space="buy", optimize=True, load=True)
    buy_pa_breadth_min = DecimalParameter(0.10, 0.90, default=0.45, decimals=2, space="buy", optimize=True, load=True)
    buy_pa_gross_cap_pct = DecimalParameter(0.05, 0.80, default=0.25, decimals=2, space="buy", optimize=False, load=True)
    buy_pa_stake_floor_mult = DecimalParameter(0.50, 1.00, default=0.80, decimals=2, space="buy", optimize=False, load=True)
    buy_pa_stake_ceiling_mult = DecimalParameter(1.00, 1.50, default=1.20, decimals=2, space="buy", optimize=False, load=True)

    sell_pa_stoploss = DecimalParameter(-0.10, -0.01, default=-0.030, decimals=3, space="sell", optimize=True, load=True)
    sell_pa_profit_target = DecimalParameter(0.01, 0.10, default=0.025, decimals=3, space="sell", optimize=True, load=True)
    sell_pa_time_stop_bars = IntParameter(1, 24, default=6, space="sell", optimize=True, load=True)
    sell_pa_rank_exit = IntParameter(2, 12, default=3, space="sell", optimize=True, load=True)
    sell_pa_score_exit = DecimalParameter(-0.20, 0.30, default=0.04, decimals=2, space="sell", optimize=True, load=True)
    sell_pa_market_off_exit = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_pa_scratch_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_pa_scratch_arm = DecimalParameter(0.002, 0.03, default=0.008, decimals=3, space="sell", optimize=True, load=True)
    sell_pa_scratch_stop = DecimalParameter(-0.005, 0.01, default=0.000, decimals=3, space="sell", optimize=True, load=True)
    sell_pa_trail_enabled = BooleanParameter(default=True, space="sell", optimize=False, load=True)
    sell_pa_trail_arm = DecimalParameter(0.004, 0.08, default=0.018, decimals=3, space="sell", optimize=True, load=True)
    sell_pa_trail_offset = DecimalParameter(0.002, 0.04, default=0.008, decimals=3, space="sell", optimize=True, load=True)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        if str(config.get("trading_mode", "spot")).lower() == "futures":
            raise ValueError("PortfolioAllocatorSpot is spot-only; use a futures strategy for perpetual markets")
        self._alloc_pair_cache: dict[str, pd.DataFrame] = {}
        self._alloc_cache_signature: tuple | None = None
        self._alloc_hwm: dict[str, float] = {}

    def load_params_from_file(self) -> dict:
        return apply_runtime_overrides({"params": {}}, self._OVERRIDES_ENV)

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

    def _alloc_trade_key(self, trade: Trade) -> str:
        return f"{getattr(trade, 'id', 'na')}|{getattr(trade, 'pair', '')}|{getattr(trade, 'open_date_utc', '')}"

    def _safe_get_open_trades(self) -> list:
        try:
            return Trade.get_open_trades()
        except Exception:
            return []

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

    def _alloc_pairs(self) -> list[str]:
        pairs = current_whitelist(self)
        out: list[str] = []
        for pair in pairs:
            asset = base_asset(pair)
            if asset == "BTC":
                continue
            if bool(self.buy_pa_majors_only.value):
                if asset not in _MAJORS_ASSETS:
                    continue
            elif bool(self.buy_pa_liquid_only.value) and asset in _TAIL_ASSETS:
                continue
            out.append(pair)
        return out

    def _alloc_signature(self) -> tuple:
        return (
            tuple(sorted(self._alloc_pairs())),
            int(self.buy_pa_momo_fast.value),
            int(self.buy_pa_momo_mid.value),
            int(self.buy_pa_momo_slow.value),
            int(self.buy_pa_relvol_len.value),
            int(self.buy_pa_ema_fast.value),
            int(self.buy_pa_ema_slow.value),
            int(self.buy_pa_topn.value),
            int(self.buy_pa_rebalance_bars.value),
            float(self.buy_pa_w_fast.value),
            float(self.buy_pa_w_mid.value),
            float(self.buy_pa_w_slow.value),
            float(self.buy_pa_relvol_min.value),
            float(self.buy_pa_atr_pct_max.value),
            float(self.buy_pa_min_score.value),
            float(self.buy_pa_btc_momo_min.value),
            float(self.buy_pa_breadth_min.value),
            bool(self.buy_pa_require_trend.value),
            bool(self.buy_pa_require_fast_positive.value),
            bool(self.buy_pa_btc_filter_enabled.value),
        )

    @staticmethod
    def _centered_rank_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()
        ranked = frame.rank(axis=1, pct=True, method="average")
        return ((ranked - 0.5) * 2.0).clip(lower=-1.0, upper=1.0)

    def _build_cache(self) -> None:
        if not bool(self.buy_pa_enabled.value):
            self._alloc_pair_cache = {}
            self._alloc_cache_signature = self._alloc_signature()
            return

        signature = self._alloc_signature()
        if self._alloc_cache_signature == signature and self._alloc_pair_cache:
            return

        pairs = self._alloc_pairs()
        btc_pair = resolve_pair_by_asset(self, "BTC")
        if len(pairs) < 2 or not btc_pair:
            self._alloc_pair_cache = {}
            self._alloc_cache_signature = signature
            return

        fast_lb = max(1, int(self.buy_pa_momo_fast.value))
        mid_lb = max(fast_lb + 1, int(self.buy_pa_momo_mid.value))
        slow_lb = max(mid_lb + 1, int(self.buy_pa_momo_slow.value))
        relvol_len = max(4, int(self.buy_pa_relvol_len.value))
        ema_fast_len = max(4, int(self.buy_pa_ema_fast.value))
        ema_slow_len = max(ema_fast_len + 1, int(self.buy_pa_ema_slow.value))

        pair_frames: dict[str, pd.DataFrame] = {}
        for pair in pairs:
            base_df = self._price_frame(pair)
            if base_df is None:
                continue
            close = pd.to_numeric(base_df.get("close"), errors="coerce")
            volume = pd.to_numeric(base_df.get("volume"), errors="coerce")
            relvol = volume / volume.rolling(relvol_len, min_periods=max(3, relvol_len // 3)).mean().replace(0.0, np.nan)
            atr_pct = ta.ATR(base_df, timeperiod=14) / close.replace(0.0, np.nan)
            ema_fast = ta.EMA(base_df, timeperiod=ema_fast_len)
            ema_slow = ta.EMA(base_df, timeperiod=ema_slow_len)

            pair_frames[pair] = pd.DataFrame(
                {
                    "pa_fast": pd.Series(close.pct_change(fast_lb).to_numpy(), index=base_df["__date"]),
                    "pa_mid": pd.Series(close.pct_change(mid_lb).to_numpy(), index=base_df["__date"]),
                    "pa_slow": pd.Series(close.pct_change(slow_lb).to_numpy(), index=base_df["__date"]),
                    "pa_relvol": pd.Series(relvol.to_numpy(), index=base_df["__date"]),
                    "pa_atr_pct": pd.Series(atr_pct.to_numpy(), index=base_df["__date"]),
                    "pa_close": pd.Series(close.to_numpy(), index=base_df["__date"]),
                    "pa_ema_fast": pd.Series(pd.to_numeric(ema_fast, errors="coerce").to_numpy(), index=base_df["__date"]),
                    "pa_ema_slow": pd.Series(pd.to_numeric(ema_slow, errors="coerce").to_numpy(), index=base_df["__date"]),
                }
            ).sort_index()

        if len(pair_frames) < 2:
            self._alloc_pair_cache = {}
            self._alloc_cache_signature = signature
            return

        fast_mat = pd.DataFrame({pair: frame["pa_fast"] for pair, frame in pair_frames.items()}).sort_index()
        mid_mat = pd.DataFrame({pair: frame["pa_mid"] for pair, frame in pair_frames.items()}).sort_index()
        slow_mat = pd.DataFrame({pair: frame["pa_slow"] for pair, frame in pair_frames.items()}).sort_index()
        relvol_mat = pd.DataFrame({pair: frame["pa_relvol"] for pair, frame in pair_frames.items()}).sort_index()
        atr_mat = pd.DataFrame({pair: frame["pa_atr_pct"] for pair, frame in pair_frames.items()}).sort_index()
        close_mat = pd.DataFrame({pair: frame["pa_close"] for pair, frame in pair_frames.items()}).sort_index()
        ema_fast_mat = pd.DataFrame({pair: frame["pa_ema_fast"] for pair, frame in pair_frames.items()}).sort_index()
        ema_slow_mat = pd.DataFrame({pair: frame["pa_ema_slow"] for pair, frame in pair_frames.items()}).sort_index()

        rank_fast = self._centered_rank_frame(fast_mat).fillna(0.0)
        rank_mid = self._centered_rank_frame(mid_mat).fillna(0.0)
        rank_slow = self._centered_rank_frame(slow_mat).fillna(0.0)

        w_fast = float(self.buy_pa_w_fast.value)
        w_mid = float(self.buy_pa_w_mid.value)
        w_slow = float(self.buy_pa_w_slow.value)
        weight_sum = max(1e-9, abs(w_fast) + abs(w_mid) + abs(w_slow))
        score = (rank_fast * w_fast + rank_mid * w_mid + rank_slow * w_slow) / weight_sum

        trend_ok = pd.DataFrame(True, index=close_mat.index, columns=close_mat.columns)
        if bool(self.buy_pa_require_trend.value):
            trend_ok = ((close_mat > ema_fast_mat) & (ema_fast_mat > ema_slow_mat)).fillna(False)

        absolute_ok = ((mid_mat > 0.0) & (slow_mat > 0.0)).fillna(False)
        if bool(self.buy_pa_require_fast_positive.value):
            absolute_ok &= (fast_mat > 0.0).fillna(False)

        relvol_ok = (relvol_mat >= float(self.buy_pa_relvol_min.value)).fillna(False)
        atr_ok = (atr_mat <= float(self.buy_pa_atr_pct_max.value)).fillna(False)

        breadth = (absolute_ok & trend_ok).sum(axis=1) / max(1, len(score.columns))

        btc_df = self._price_frame(btc_pair)
        btc_market_on = pd.Series(True, index=score.index, dtype=bool)
        if btc_df is not None and not btc_df.empty and bool(self.buy_pa_btc_filter_enabled.value):
            btc_close = pd.to_numeric(btc_df.get("close"), errors="coerce")
            btc_ema_fast = pd.to_numeric(ta.EMA(btc_df, timeperiod=max(4, int(self.buy_pa_btc_ema_fast.value))), errors="coerce")
            btc_ema_slow = pd.to_numeric(ta.EMA(btc_df, timeperiod=max(8, int(self.buy_pa_btc_ema_slow.value))), errors="coerce")
            btc_momo = pd.to_numeric(btc_close.pct_change(max(1, int(self.buy_pa_btc_momo_lb.value))), errors="coerce")
            btc_work = pd.DataFrame(
                {
                    "__date": pd.to_datetime(btc_df["__date"], utc=True, errors="coerce"),
                    "btc_close": btc_close,
                    "btc_ema_fast": btc_ema_fast,
                    "btc_ema_slow": btc_ema_slow,
                    "btc_momo": btc_momo,
                }
            ).dropna(subset=["__date"]).sort_values("__date")
            breadth_idx = pd.DataFrame({"__date": score.index}).sort_values("__date")
            merged = pd.merge_asof(breadth_idx, btc_work, on="__date", direction="backward")
            btc_market_on = (
                (pd.to_numeric(merged["btc_close"], errors="coerce") > pd.to_numeric(merged["btc_ema_fast"], errors="coerce"))
                & (pd.to_numeric(merged["btc_ema_fast"], errors="coerce") > pd.to_numeric(merged["btc_ema_slow"], errors="coerce"))
                & (pd.to_numeric(merged["btc_momo"], errors="coerce") >= float(self.buy_pa_btc_momo_min.value))
            ).fillna(False)
            btc_market_on.index = score.index

        market_on = (btc_market_on & (breadth >= float(self.buy_pa_breadth_min.value)).fillna(False)).fillna(False)

        long_rank = score.rank(axis=1, ascending=False, method="min")
        selected = (long_rank <= int(self.buy_pa_topn.value)) & (score >= float(self.buy_pa_min_score.value))
        selected &= relvol_ok & atr_ok & trend_ok & absolute_ok
        selected = selected.mul(market_on, axis=0).fillna(False)

        cache: dict[str, pd.DataFrame] = {}
        for pair in pair_frames:
            cache[pair] = pd.DataFrame(
                {
                    "date": score.index,
                    "pa_score": pd.to_numeric(score[pair], errors="coerce").values,
                    "pa_rank": pd.to_numeric(long_rank[pair], errors="coerce").values,
                    "pa_relvol": pd.to_numeric(relvol_mat[pair], errors="coerce").values,
                    "pa_atr_pct": pd.to_numeric(atr_mat[pair], errors="coerce").values,
                    "pa_selected": selected[pair].fillna(False).astype(bool).values,
                    "pa_market_on": market_on.fillna(False).astype(bool).values,
                    "pa_breadth": pd.to_numeric(breadth, errors="coerce").values,
                }
            ).dropna(subset=["date"]).sort_values("date")

        self._alloc_pair_cache = cache
        self._alloc_cache_signature = signature

    def _merge_pair_cache(self, dataframe: DataFrame, pair: str) -> DataFrame:
        self._build_cache()
        cached = self._alloc_pair_cache.get(pair)
        if cached is None or cached.empty:
            out = dataframe.copy()
            out["pa_score"] = np.nan
            out["pa_rank"] = np.nan
            out["pa_relvol"] = np.nan
            out["pa_atr_pct"] = np.nan
            out["pa_selected"] = False
            out["pa_market_on"] = False
            out["pa_breadth"] = np.nan
            return out

        left = dataframe.copy()
        left["__alloc_date"] = pd.to_datetime(left["date"], utc=True, errors="coerce")
        left = left.sort_values("__alloc_date")
        right = cached.copy().rename(columns={"date": "__alloc_date"}).sort_values("__alloc_date")
        merged = pd.merge_asof(left, right, on="__alloc_date", direction="backward").sort_index()
        merged.drop(columns=["__alloc_date"], inplace=True, errors="ignore")
        merged["pa_selected"] = merged["pa_selected"].fillna(False).astype(bool)
        merged["pa_market_on"] = merged["pa_market_on"].fillna(False).astype(bool)
        return merged

    def _pair_row_at_or_before_time(self, pair: str, when) -> pd.Series | None:
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        except Exception:
            return None
        if dataframe is None or dataframe.empty or "date" not in dataframe.columns:
            return None
        ts = pd.Timestamp(when)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        rows = dataframe.loc[pd.to_datetime(dataframe["date"], utc=True, errors="coerce") <= ts]
        if rows.empty:
            return None
        return rows.iloc[-1]

    def _open_alloc_count(self) -> int:
        count = 0
        for trade in self._safe_get_open_trades():
            tag = str(getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or "")
            if tag.startswith("pa_long"):
                count += 1
        return count

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if not bool(self.buy_pa_enabled.value):
            return dataframe.copy()
        return self._merge_pair_cache(dataframe, metadata["pair"])

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "enter_long"] = 0
        dataframe.loc[:, "enter_short"] = 0
        dataframe.loc[:, "enter_tag"] = ""

        if not bool(self.buy_pa_enabled.value):
            return dataframe

        mask = dataframe.get("pa_selected", False)
        if isinstance(mask, pd.Series):
            mask = mask.fillna(False).astype(bool)
        else:
            mask = pd.Series(False, index=dataframe.index, dtype=bool)
        mask &= (dataframe["volume"] > 0).fillna(False)

        rebalance_bars = max(1, int(self.buy_pa_rebalance_bars.value))
        if rebalance_bars > 1:
            eligible = (pd.Series(np.arange(len(dataframe)), index=dataframe.index) % rebalance_bars).eq(0)
            mask &= eligible.fillna(False)

        dataframe.loc[mask, "enter_long"] = 1
        dataframe.loc[mask, "enter_tag"] = "pa_long"
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
        current_time,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        if side != "long" or not str(entry_tag or "").startswith("pa_long"):
            return False
        row = self._pair_row_at_or_before_time(pair, current_time)
        if row is None:
            return False
        if not bool(row.get("pa_selected", False)):
            return False
        if self._open_alloc_count() >= int(self.buy_pa_topn.value):
            return False
        return True

    def custom_stake_amount(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        if not str(entry_tag or "").startswith("pa_long"):
            return float(proposed_stake)

        total_slots = max(1, int(self.buy_pa_topn.value))
        base_cap = float(self._wallet_total()) * float(self.buy_pa_gross_cap_pct.value) / float(total_slots)

        strength = 1.0
        row = self._pair_row_at_or_before_time(pair, current_time)
        if row is not None:
            score = abs(float(row.get("pa_score", 0.0) or 0.0))
            threshold = max(0.05, float(self.buy_pa_min_score.value))
            strength = float(
                np.clip(
                    score / threshold,
                    float(self.buy_pa_stake_floor_mult.value),
                    float(self.buy_pa_stake_ceiling_mult.value),
                )
            )

        stake = min(float(proposed_stake), float(max_stake), float(base_cap) * float(strength))
        if min_stake is not None and stake < float(min_stake):
            return 0.0
        return max(0.0, float(stake))

    def leverage(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return 1.0

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        tag = str(getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or "")
        if not tag.startswith("pa_"):
            return self.stoploss

        desired_open_profit = float(self.sell_pa_stoploss.value)
        key = self._alloc_trade_key(trade)
        hwm = float(self._alloc_hwm.get(key, current_profit))
        if float(current_profit) > hwm:
            hwm = float(current_profit)
        self._alloc_hwm[key] = hwm

        if bool(self.sell_pa_scratch_enabled.value) and hwm >= float(self.sell_pa_scratch_arm.value):
            desired_open_profit = max(desired_open_profit, float(self.sell_pa_scratch_stop.value))
        if bool(self.sell_pa_trail_enabled.value) and hwm >= float(self.sell_pa_trail_arm.value):
            desired_open_profit = max(desired_open_profit, hwm - float(self.sell_pa_trail_offset.value))

        alloc_sl = stoploss_from_open(
            float(desired_open_profit),
            float(current_profit),
            is_short=trade.is_short,
            leverage=trade.leverage,
        )
        return float(alloc_sl) if alloc_sl is not None else 1.0

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | None:
        tag = str(getattr(trade, "enter_tag", None) or getattr(trade, "entry_tag", None) or "")
        if not tag.startswith("pa_"):
            return None

        row = self._pair_row_at_or_before_time(pair, current_time)
        age_bars = 0.0
        try:
            age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600.0
            age_bars = age_hours / 4.0
        except Exception:
            pass

        if row is not None:
            market_on = bool(row.get("pa_market_on", False))
            score = float(row.get("pa_score", np.nan))
            rank = float(row.get("pa_rank", np.nan))
            if bool(self.sell_pa_market_off_exit.value) and not market_on:
                return "pa_market_off"
            if np.isfinite(rank) and rank > float(self.sell_pa_rank_exit.value):
                return "pa_rank_exit"
            if np.isfinite(score) and score <= float(self.sell_pa_score_exit.value):
                return "pa_score_exit"

        if current_profit >= float(self.sell_pa_profit_target.value):
            return "pa_tp"

        if age_bars >= float(self.sell_pa_time_stop_bars.value):
            return "pa_time_stop"

        return None
