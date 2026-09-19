"""Fail-closed funding/basis carry lane.

The strategy deliberately produces no entries unless exact-venue historical
funding, mark, and index candles are available for the same pair and period.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from freqtrade.strategy import DecimalParameter, IStrategy
from pandas import DataFrame

try:
    from user_data.strategies.market_context import derivative_candle_types
except ModuleNotFoundError:  # Direct strategy-module imports in focused tests.
    from market_context import derivative_candle_types


class FundingBasisCarry(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 48
    stoploss = -0.08
    minimal_roi = {"0": 100.0}

    buy_carry_funding_min = DecimalParameter(0.0001, 0.02, default=0.0005, decimals=4, space="buy", optimize=True)
    buy_carry_basis_max = DecimalParameter(0.0001, 0.05, default=0.005, decimals=4, space="buy", optimize=True)
    sell_carry_basis_exit = DecimalParameter(0.0, 0.02, default=0.001, decimals=4, space="sell", optimize=True)

    def informative_pairs(self):
        pairs = list(self.config.get("exchange", {}).get("pair_whitelist", []))
        result = []
        for pair in pairs:
            for candle_type in (*derivative_candle_types(self.config), "funding_rate", "mark", "index"):
                item = (pair, self.timeframe, candle_type)
                if item not in result:
                    result.append(item)
        return result

    def _source(self, pair: str, candle_type: str) -> DataFrame | None:
        try:
            frame = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe, candle_type=candle_type)
        except Exception:
            return None
        return frame if frame is not None and not frame.empty else None

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = str(metadata.get("pair", ""))
        dataframe["carry_funding"] = np.nan
        dataframe["carry_basis"] = np.nan
        funding = self._source(pair, "funding_rate")
        mark = self._source(pair, "mark")
        index = self._source(pair, "index")
        if funding is None or mark is None or index is None:
            dataframe["enter_long"] = 0
            dataframe["enter_short"] = 0
            return dataframe
        left = dataframe.copy()
        left["__date"] = pd.to_datetime(left["date"], utc=True, errors="coerce")
        def close_series(frame: DataFrame, name: str) -> DataFrame:
            out = frame[["date", "close"]].copy()
            out["__date"] = pd.to_datetime(out["date"], utc=True, errors="coerce")
            out[name] = pd.to_numeric(out["close"], errors="coerce")
            return out[["__date", name]].dropna(subset=["__date"]).sort_values("__date")
        merged = pd.merge_asof(left.sort_values("__date"), close_series(mark, "mark_close"), on="__date", direction="backward")
        merged = pd.merge_asof(merged.sort_values("__date"), close_series(index, "index_close"), on="__date", direction="backward")
        fcol = next((c for c in ("funding_rate", "funding", "rate", "close") if c in funding.columns), None)
        if fcol is None:
            return dataframe.assign(enter_long=0, enter_short=0)
        f = funding[["date", fcol]].copy()
        f["__date"] = pd.to_datetime(f["date"], utc=True, errors="coerce")
        f["carry_funding"] = pd.to_numeric(f[fcol], errors="coerce")
        merged = pd.merge_asof(merged.sort_values("__date"), f[["__date", "carry_funding"]].dropna(subset=["__date"]).sort_values("__date"), on="__date", direction="backward")
        merged["carry_basis"] = (merged["mark_close"] - merged["index_close"]) / merged["index_close"].replace(0, np.nan)
        dataframe["carry_funding"] = merged["carry_funding"].to_numpy()
        dataframe["carry_basis"] = merged["carry_basis"].to_numpy()
        valid = dataframe["carry_funding"].notna() & dataframe["carry_basis"].notna()
        dataframe["enter_long"] = (valid & dataframe["carry_funding"].le(-float(self.buy_carry_funding_min.value)) & dataframe["carry_basis"].le(float(self.buy_carry_basis_max.value))).astype(int)
        dataframe["enter_short"] = (valid & dataframe["carry_funding"].ge(float(self.buy_carry_funding_min.value)) & dataframe["carry_basis"].ge(-float(self.buy_carry_basis_max.value))).astype(int)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_tag"] = np.where(dataframe.get("enter_long", 0), "carry_long", np.where(dataframe.get("enter_short", 0), "carry_short", ""))
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = dataframe["carry_basis"].abs().le(float(self.sell_carry_basis_exit.value)).astype(int)
        dataframe["exit_short"] = dataframe["carry_basis"].abs().le(float(self.sell_carry_basis_exit.value)).astype(int)
        dataframe["exit_tag"] = "carry_convergence"
        return dataframe
