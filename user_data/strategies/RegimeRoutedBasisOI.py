"""Opt-in basis/open-interest interaction validation lane."""

from __future__ import annotations

import pandas as pd
from freqtrade.strategy import BooleanParameter, IntParameter

from RegimeRouted import RegimeRouted
from market_context import derivative_candle_types


class RegimeRoutedBasisOI(RegimeRouted):
    """Require basis/OI data quality for the router; never substitute prices."""

    buy_deriv_dq_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_deriv_dq_apply_aux_only = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_deriv_dq_use_funding = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_deriv_dq_use_oi = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_deriv_dq_use_basis = BooleanParameter(default=True, space="buy", optimize=False, load=True)
    buy_deriv_dq_allow_missing = BooleanParameter(default=False, space="buy", optimize=False, load=True)
    buy_deriv_dq_require_proxy_count = IntParameter(2, 2, default=2, space="buy", optimize=False, load=True)
    buy_basis_rank_enabled = BooleanParameter(default=True, space="buy", optimize=False, load=True)

    def informative_pairs(self):
        result = list(super().informative_pairs())
        candle_types = derivative_candle_types({"trading_mode": "futures"})
        for pair in self.dp.current_whitelist():
            for candle_type in (*candle_types, "open_interest"):
                item = (pair, self.timeframe, candle_type)
                if item not in result:
                    result.append(item)
        return result

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        # The parent computes basis from mark/index.  Add OI change only when
        # the exchange supplied an open-interest candle for this exact pair.
        dataframe = super().populate_indicators(dataframe, metadata)
        pair = metadata["pair"]
        try:
            oi = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe, candle_type="open_interest")
        except Exception:
            oi = None
        if oi is None or oi.empty or "date" not in oi:
            dataframe["oi_change_pct"] = float("nan")
            return dataframe
        src = oi.copy()
        src["date"] = pd.to_datetime(src["date"], utc=True, errors="coerce")
        value_col = next((c for c in ("open_interest_amount", "open_interest_value", "open_interest", "oi") if c in src), None)
        if value_col is None:
            dataframe["oi_change_pct"] = float("nan")
            return dataframe
        src["__oi"] = pd.to_numeric(src[value_col], errors="coerce")
        left = dataframe.copy()
        left["__date"] = pd.to_datetime(left["date"], utc=True, errors="coerce")
        right = src[["date", "__oi"]].rename(columns={"date": "__date"}).dropna(subset=["__date"]).sort_values("__date")
        left = left.sort_values("__date")
        merged = pd.merge_asof(left, right, on="__date", direction="backward").sort_index()
        dataframe["oi_change_pct"] = pd.to_numeric(merged["__oi"], errors="coerce").pct_change()
        return dataframe
