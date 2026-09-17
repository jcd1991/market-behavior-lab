"""
Regime Detector V54 Enhanced — Freqtrade-compatible DataFrame indicator.

Zero external dependencies beyond pandas/numpy (which Freqtrade already requires).

Produces 33 regime columns that can be consumed by any IStrategy subclass.

Usage in a Freqtrade strategy::

    from lib.regime_detector import populate_regime_indicators

    class MyStrategy(IStrategy):
        def populate_indicators(self, dataframe, metadata):
            dataframe = populate_regime_indicators(dataframe)
            return dataframe

Columns added (full list in REGIME_COLUMNS):
    regime_id, atr_phase, market_state, base_regime, vol_state, trend_dir,
    composite_regime, er, chop, atr_raw, atr_pct, bb_width, bb_width_percentile,
    atr_percentile, vol_regime, swept_up, swept_down, wick_ratio, reclaimed,
    sweep_flag, capitulation_flag, tr_over_atr, vol_zscore, ret_zscore,
    volume_percentile, bars_since_flip, confidence, range_z,
    volume_percentile_frac, reclaim_frac, impulse_dir, sweep_bars_since,
    liquidity_quality

Original implementation for Market Behavior Lab.

Project history: This module originated in the earlier aitrader prototype
and was migrated to the Freqtrade runtime.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════

class RegimeID(Enum):
    OFF = "OFF"
    CHOP_LV = "CHOP_LV"
    CHOP_HV = "CHOP_HV"
    TREND = "TREND"


class ATRPhase(Enum):
    EXPAND = "EXPAND"
    CONTRACT = "CONTRACT"
    NEUTRAL = "NEUTRAL"


class MarketState(Enum):
    CHOP_STABLE = "CHOP_STABLE"
    COMPRESSION = "COMPRESSION"
    TREND_EARLY = "TREND_EARLY"
    TREND_STABLE = "TREND_STABLE"


class VolumeRegime(Enum):
    VOL_LOW = "VOL_LOW"
    VOL_NORMAL = "VOL_NORMAL"
    VOL_HIGH = "VOL_HIGH"


class TrendDirection(Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    FLAT = "FLAT"


class RegimeType(Enum):
    CHOP_LOW = "CHOP_LOW"
    CHOP_HIGH = "CHOP_HIGH"
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    DOWN_LOW = "DOWN_LOW"
    DOWN_NORMAL = "DOWN_NORMAL"
    DOWN_HIGH = "DOWN_HIGH"
    WARMUP = "WARMUP"
    UNKNOWN = "UNKNOWN"


# ════════════════════════════════════════════════════════════════
# Configuration
# ════════════════════════════════════════════════════════════════

@dataclass
class RegimeConfig:
    """All detector parameters — every one is hyperopt-able."""

    # Efficiency Ratio
    er_len: int = 24
    er_trend_min: float = 0.55

    # Choppiness Index
    chop_len: int = 14
    chop_trend_max: float = 38.2

    # ATR
    atr_len: int = 14
    atr_hv_min_pct: float = 0.015
    atr_lv_max_pct: float = 0.008

    # ATR ROC
    atr_roc_len: int = 10
    atr_roc_expand_q: float = 0.05
    atr_roc_contract_q: float = -0.05

    # Hysteresis
    confirm_bars: int = 2
    cooldown_bars: int = 3

    # Bollinger Bands
    bb_len: int = 20
    bb_std: float = 2.0

    # BBW Compression
    bbw_lookback: int = 100
    bbw_compression_pctl: float = 20.0

    # ATR Percentile
    atr_pctl_lookback: int = 240
    atr_vol_low_pctl: float = 20.0
    atr_vol_high_pctl: float = 80.0

    # Sweep / Trap
    sweep_lookback: int = 20
    wick_ratio_threshold: float = 1.5
    reclaim_lookback: int = 5

    # State machine
    trend_early_bars: int = 5

    # Capitulation
    capitulation_bbw_pctl: float = 90.0
    capitulation_tr_over_atr: float = 2.0
    capitulation_ret_z: float = -1.6
    capitulation_volume_pctl: float = 90.0
    capitulation_ret_lookback: int = 5
    capitulation_z_window: int = 120

    # Trend direction
    trend_dir_lookback: int = 10
    trend_dir_threshold: float = 0.001


# ════════════════════════════════════════════════════════════════
# Pure-numpy indicator functions (vectorised where possible)
# ════════════════════════════════════════════════════════════════

def _efficiency_ratio(close: np.ndarray, length: int) -> np.ndarray:
    """Kaufman Efficiency Ratio, vectorised."""
    n = len(close)
    er = np.full(n, np.nan)
    for i in range(length, n):
        window = close[i - length + 1: i + 1]
        net = abs(window[-1] - window[0])
        diffs = np.abs(np.diff(window))
        total = diffs.sum()
        er[i] = net / total if total > 0 else 0.0
    return er


def _choppiness_index(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                      length: int) -> np.ndarray:
    """Choppiness Index, vectorised."""
    n = len(close)
    ci = np.full(n, np.nan)
    for i in range(length, n):
        sl = slice(i - length + 1, i + 1)
        h, l, c = high[sl], low[sl], close[sl]
        prev_c = close[i - length: i]
        tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
        tr_sum = tr.sum()
        hh, ll = h.max(), l.min()
        if hh <= ll or tr_sum == 0:
            ci[i] = 50.0
        else:
            ci[i] = 100.0 * np.log10(tr_sum / (hh - ll)) / np.log10(length)
    return ci


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
         length: int) -> np.ndarray:
    """Average True Range, vectorised."""
    n = len(close)
    out = np.full(n, np.nan)
    for i in range(length, n):
        sl = slice(i - length + 1, i + 1)
        h, l = high[sl], low[sl]
        prev_c = close[i - length: i]
        tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
        out[i] = tr.mean()
    return out


def _bollinger_bandwidth(close: np.ndarray, length: int,
                         std_mult: float = 2.0) -> np.ndarray:
    """BBW = (upper - lower) / middle."""
    n = len(close)
    bbw = np.full(n, np.nan)
    for i in range(length - 1, n):
        window = close[i - length + 1: i + 1]
        sma = window.mean()
        std = window.std(ddof=0)
        if sma == 0:
            bbw[i] = 0.0
        else:
            bbw[i] = (2 * std_mult * std) / sma
    return bbw


def _rolling_percentile_rank(values: np.ndarray, lookback: int) -> np.ndarray:
    """Percentile rank of each value within its trailing window."""
    n = len(values)
    out = np.full(n, 50.0)
    for i in range(1, n):
        start = max(0, i - lookback)
        window = values[start: i + 1]
        valid = window[~np.isnan(window)]
        if len(valid) == 0:
            continue
        out[i] = (np.sum(valid < values[i]) / len(valid)) * 100.0
    return out


def _detect_sweeps(high: np.ndarray, low: np.ndarray, open_: np.ndarray,
                   close: np.ndarray, lookback: int) -> tuple:
    """Vectorised sweep / wick_ratio / reclaim detection."""
    n = len(close)
    swept_up = np.zeros(n, dtype=bool)
    swept_down = np.zeros(n, dtype=bool)
    wick_ratio = np.zeros(n, dtype=float)
    reclaimed = np.zeros(n, dtype=bool)

    for i in range(lookback + 1, n):
        prior_h = high[i - lookback: i].max()
        prior_l = low[i - lookback: i].min()
        swept_up[i] = high[i] > prior_h
        swept_down[i] = low[i] < prior_l
        body = abs(close[i] - open_[i])
        wick = high[i] - low[i]
        wick_ratio[i] = wick / body if body > 0 else 0.0
        if swept_up[i] and close[i] < (open_[i] + body * 0.3):
            reclaimed[i] = True
        elif swept_down[i] and close[i] > (open_[i] - body * 0.3):
            reclaimed[i] = True

    return swept_up, swept_down, wick_ratio, reclaimed


# ════════════════════════════════════════════════════════════════
# Composite Regime Classification
# ════════════════════════════════════════════════════════════════

def _classify_composite(base_regime: str, vol_regime: str,
                        trend_dir: str) -> str:
    """
    Map (base_regime, vol_regime, trend_dir) → RegimeType string.

    Mirrors the project's earlier regime-type classification.
    """
    if base_regime in ("CHOP", "CHOP_LV", "CHOP_HV"):
        if vol_regime == "VOL_LOW":
            return "CHOP_LOW"
        elif vol_regime == "VOL_HIGH":
            return "CHOP_HIGH"
        else:
            return "CHOP_LOW"  # VOL_NORMAL treated conservatively
    elif base_regime == "TREND":
        if trend_dir == "DOWN":
            if vol_regime == "VOL_LOW":
                return "DOWN_LOW"
            elif vol_regime == "VOL_HIGH":
                return "DOWN_HIGH"
            else:
                return "DOWN_NORMAL"
        else:
            return "TREND_UP"
    # Fallback for non-TREND base + DOWN direction
    if trend_dir == "DOWN":
        if vol_regime == "VOL_HIGH":
            return "DOWN_HIGH"
        elif vol_regime == "VOL_NORMAL":
            return "DOWN_NORMAL"
        else:
            return "DOWN_LOW"
    return "UNKNOWN"


# ════════════════════════════════════════════════════════════════
# Main entry point: populate_regime_indicators()
# ════════════════════════════════════════════════════════════════

REGIME_COLUMNS = [
    "regime_id", "atr_phase", "market_state",
    "base_regime", "vol_state", "trend_dir", "composite_regime",
    "er", "chop", "atr_raw", "atr_pct",
    "bb_width", "bb_width_percentile",
    "atr_percentile", "vol_regime",
    "swept_up", "swept_down", "wick_ratio", "reclaimed",
    "sweep_flag", "capitulation_flag",
    "tr_over_atr", "vol_zscore", "ret_zscore", "volume_percentile",
    "bars_since_flip", "confidence",
    "range_z", "volume_percentile_frac", "reclaim_frac",
    "impulse_dir", "sweep_bars_since", "liquidity_quality",
]


def populate_regime_indicators(
    dataframe: pd.DataFrame,
    config: Optional[RegimeConfig] = None,
    prefix: str = "",
) -> pd.DataFrame:
    """
    Add all regime indicator columns to a Freqtrade OHLCV dataframe.

    Parameters
    ----------
    dataframe : pd.DataFrame
        Must contain columns: open, high, low, close, volume.
    config : RegimeConfig, optional
        Detector tuning parameters. Uses validated defaults if None.
    prefix : str, optional
        Column name prefix (e.g. "regime_" → "regime_er", "regime_chop").

    Returns
    -------
    pd.DataFrame
        The same dataframe, with REGIME_COLUMNS added (prefixed).
    """
    cfg = config or RegimeConfig()
    p = prefix

    o = dataframe["open"].values.astype(float)
    h = dataframe["high"].values.astype(float)
    l = dataframe["low"].values.astype(float)
    c = dataframe["close"].values.astype(float)
    v = dataframe["volume"].values.astype(float)
    n = len(c)

    # ── Core indicators ────────────────────────────────────────
    er = _efficiency_ratio(c, cfg.er_len)
    chop = _choppiness_index(h, l, c, cfg.chop_len)
    atr_vals = _atr(h, l, c, cfg.atr_len)
    atr_pct = np.where(c > 0, atr_vals / c, 0.0)
    bbw = _bollinger_bandwidth(c, cfg.bb_len, cfg.bb_std)

    # ── ATR phase (ROC of ATR) ─────────────────────────────────
    atr_phase = np.full(n, "NEUTRAL", dtype=object)
    for i in range(cfg.atr_roc_len + cfg.atr_len, n):
        prev = atr_vals[i - cfg.atr_roc_len]
        if np.isnan(prev) or prev == 0:
            continue
        roc = (atr_vals[i] - prev) / prev
        if roc > cfg.atr_roc_expand_q:
            atr_phase[i] = "EXPAND"
        elif roc < cfg.atr_roc_contract_q:
            atr_phase[i] = "CONTRACT"

    # ── BBW percentile ─────────────────────────────────────────
    bbw_pctl = _rolling_percentile_rank(bbw, cfg.bbw_lookback)

    # ── ATR percentile → vol_regime ────────────────────────────
    atr_pctl = _rolling_percentile_rank(atr_vals, cfg.atr_pctl_lookback)
    vol_regime = np.full(n, "MED", dtype=object)
    vol_regime[atr_pctl <= cfg.atr_vol_low_pctl] = "LOW"
    vol_regime[atr_pctl >= cfg.atr_vol_high_pctl] = "HIGH"

    # ── Sweep / Trap ───────────────────────────────────────────
    swept_up, swept_down, wick_ratio, reclaimed = _detect_sweeps(
        h, l, o, c, cfg.sweep_lookback
    )
    sweep_flag = swept_up | swept_down

    # ── Capitulation indicators ────────────────────────────────
    # True Range / ATR ratio
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    tr_over_atr = np.where(atr_vals > 0, tr / atr_vals, 0.0)

    # Return z-score
    ret_lb = cfg.capitulation_ret_lookback
    zw = cfg.capitulation_z_window
    ret = np.zeros(n)
    for i in range(ret_lb, n):
        if c[i - ret_lb] != 0:
            ret[i] = (c[i] - c[i - ret_lb]) / c[i - ret_lb]
    ret_zscore = np.zeros(n)
    for i in range(zw, n):
        window = ret[max(0, i - zw + 1): i + 1]
        mu, sigma = window.mean(), window.std()
        ret_zscore[i] = (ret[i] - mu) / sigma if sigma > 1e-9 else 0.0

    # Volume percentile + z-score
    vol_pctl_arr = _rolling_percentile_rank(v, cfg.atr_pctl_lookback)
    vol_zscore = np.zeros(n)
    for i in range(zw, n):
        window = v[max(0, i - zw + 1): i + 1]
        mu, sigma = window.mean(), window.std()
        vol_zscore[i] = (v[i] - mu) / sigma if sigma > 1e-9 else 0.0

    # range_z (TR/ATR z-score)
    range_z = np.zeros(n)
    for i in range(zw, n):
        window = tr_over_atr[max(0, i - zw + 1): i + 1]
        mu, sigma = window.mean(), window.std()
        range_z[i] = (tr_over_atr[i] - mu) / sigma if sigma > 1e-9 else 0.0

    # Capitulation flag (multi-condition)
    sweep_capitulation = (
        sweep_flag
        & (vol_pctl_arr >= cfg.capitulation_volume_pctl)
        & (vol_zscore >= 2.0)
        & (atr_phase == "EXPAND")
    )
    liq_proxy = (
        (swept_down & reclaimed & (wick_ratio >= cfg.wick_ratio_threshold))
        | (swept_up & reclaimed & (wick_ratio >= cfg.wick_ratio_threshold))
    )
    bbw_cap = (
        (bbw_pctl >= cfg.capitulation_bbw_pctl)
        & (tr_over_atr >= cfg.capitulation_tr_over_atr)
        & (ret_zscore <= cfg.capitulation_ret_z)
        & (vol_pctl_arr >= cfg.capitulation_volume_pctl)
    )
    capitulation_flag = sweep_capitulation | bbw_cap | liq_proxy

    # ── Sweep tracking (impulse_dir, reclaim_frac, sweep_bars_since) ──
    impulse_dir = np.full(n, "", dtype=object)
    sweep_bars_since = np.full(n, 999, dtype=int)
    reclaim_frac = np.zeros(n)
    last_sweep_idx = -999
    last_sweep_dir = ""
    last_sweep_lo = 0.0
    last_sweep_hi = 0.0

    for i in range(n):
        if swept_down[i]:
            last_sweep_idx = i
            last_sweep_dir = "DOWN"
            last_sweep_lo = float(l[i])
            last_sweep_hi = float(h[i])
        elif swept_up[i]:
            last_sweep_idx = i
            last_sweep_dir = "UP"
            last_sweep_lo = float(l[i])
            last_sweep_hi = float(h[i])

        gap = i - last_sweep_idx
        sweep_bars_since[i] = gap if last_sweep_idx >= 0 else 999

        if (
            last_sweep_dir in ("UP", "DOWN")
            and gap <= cfg.reclaim_lookback
            and last_sweep_hi > last_sweep_lo
        ):
            sweep_range = last_sweep_hi - last_sweep_lo
            if last_sweep_dir == "DOWN":
                rf = (c[i] - last_sweep_lo) / sweep_range
            else:
                rf = (last_sweep_hi - c[i]) / sweep_range
            reclaim_frac[i] = max(0.0, min(1.0, rf))
            impulse_dir[i] = last_sweep_dir
        # else impulse_dir stays ""

    # ── Base regime with hysteresis ────────────────────────────
    regime_id_arr = np.full(n, "OFF", dtype=object)
    last_regime = "OFF"
    confirm_count = 0
    cooldown = 0
    bars_since_flip_arr = np.zeros(n, dtype=int)
    bsf = 0

    for i in range(n):
        if np.isnan(er[i]) or np.isnan(chop[i]) or np.isnan(atr_pct[i]):
            regime_id_arr[i] = "OFF"
            bars_since_flip_arr[i] = bsf
            continue

        is_trend = (er[i] >= cfg.er_trend_min) and (chop[i] <= cfg.chop_trend_max)
        is_hv = atr_pct[i] >= cfg.atr_hv_min_pct
        if is_trend:
            candidate = "TREND"
        elif is_hv:
            candidate = "CHOP_HV"
        else:
            candidate = "CHOP_LV"
        if atr_phase[i] == "EXPAND" and is_hv:
            candidate = "OFF"

        # Hysteresis: confirm + cooldown
        if cooldown > 0:
            cooldown -= 1
            candidate = last_regime
        if candidate != last_regime:
            confirm_count += 1
            if confirm_count >= cfg.confirm_bars:
                last_regime = candidate
                confirm_count = 0
                cooldown = cfg.cooldown_bars
                bsf = 0
        else:
            confirm_count = 0
            bsf += 1

        regime_id_arr[i] = last_regime
        bars_since_flip_arr[i] = bsf

    # ── Market state machine ───────────────────────────────────
    market_state = np.full(n, "CHOP_STABLE", dtype=object)
    for i in range(n):
        if bbw_pctl[i] <= cfg.bbw_compression_pctl:
            market_state[i] = "COMPRESSION"
        elif regime_id_arr[i] == "TREND":
            if bars_since_flip_arr[i] < cfg.trend_early_bars:
                market_state[i] = "TREND_EARLY"
            else:
                market_state[i] = "TREND_STABLE"

    # ── Confidence ─────────────────────────────────────────────
    confidence = np.full(n, 0.5)
    for i in range(n):
        if np.isnan(er[i]):
            continue
        if regime_id_arr[i] == "TREND":
            confidence[i] = min(1.0, 0.5 + (er[i] - cfg.er_trend_min) * 1.5)
        else:
            chop_val = chop[i] if not np.isnan(chop[i]) else 50.0
            confidence[i] = min(1.0, 0.5 + max(0.0, chop_val - cfg.chop_trend_max) / 50.0)

    # ── Phase-1 labels ─────────────────────────────────────────
    base_regime = np.where(regime_id_arr == "TREND", "TREND", "CHOP")
    vol_state = np.where(vol_regime == "LOW", "VOL_LOW",
                np.where(vol_regime == "HIGH", "VOL_HIGH", "VOL_NORMAL"))

    # Trend direction
    trend_dir = np.full(n, "FLAT", dtype=object)
    tl = cfg.trend_dir_lookback
    for i in range(tl, n):
        prev_c_val = c[i - tl]
        if prev_c_val == 0:
            continue
        ret_val = (c[i] - prev_c_val) / prev_c_val
        if ret_val > cfg.trend_dir_threshold:
            trend_dir[i] = "UP"
        elif ret_val < -cfg.trend_dir_threshold:
            trend_dir[i] = "DOWN"

    # Composite regime = base + vol + direction + atr_phase
    composite_regime = np.full(n, "WARMUP", dtype=object)
    for i in range(n):
        if np.isnan(er[i]):
            composite_regime[i] = "WARMUP"
            continue
        comp = _classify_composite(base_regime[i], vol_state[i], trend_dir[i])
        full = f"{comp}_{atr_phase[i]}"
        if capitulation_flag[i] and atr_phase[i] == "EXPAND":
            full = "DOWN_HIGH_CAPITULATION"
        composite_regime[i] = full

    # ── Derived: volume_percentile_frac, liquidity_quality ─────
    vol_pctl_frac = np.clip(vol_pctl_arr / 100.0, 0, 1)
    liquidity_quality = np.clip(
        vol_pctl_frac * 0.55 + np.clip(vol_zscore, 0, 4) / 4.0 * 0.45,
        0, 1,
    )

    # ── Write all columns ─────────────────────────────────────
    dataframe[f"{p}regime_id"] = regime_id_arr
    dataframe[f"{p}atr_phase"] = atr_phase
    dataframe[f"{p}market_state"] = market_state
    dataframe[f"{p}base_regime"] = base_regime
    dataframe[f"{p}vol_state"] = vol_state
    dataframe[f"{p}trend_dir"] = trend_dir
    dataframe[f"{p}composite_regime"] = composite_regime
    dataframe[f"{p}er"] = er
    dataframe[f"{p}chop"] = chop
    dataframe[f"{p}atr_raw"] = atr_vals
    dataframe[f"{p}atr_pct"] = atr_pct
    dataframe[f"{p}bb_width"] = bbw
    dataframe[f"{p}bb_width_percentile"] = bbw_pctl
    dataframe[f"{p}atr_percentile"] = atr_pctl
    dataframe[f"{p}vol_regime"] = vol_regime
    dataframe[f"{p}swept_up"] = swept_up
    dataframe[f"{p}swept_down"] = swept_down
    dataframe[f"{p}wick_ratio"] = wick_ratio
    dataframe[f"{p}reclaimed"] = reclaimed
    dataframe[f"{p}sweep_flag"] = sweep_flag
    dataframe[f"{p}capitulation_flag"] = capitulation_flag
    dataframe[f"{p}tr_over_atr"] = tr_over_atr
    dataframe[f"{p}vol_zscore"] = vol_zscore
    dataframe[f"{p}ret_zscore"] = ret_zscore
    dataframe[f"{p}volume_percentile"] = vol_pctl_arr
    dataframe[f"{p}bars_since_flip"] = bars_since_flip_arr
    dataframe[f"{p}confidence"] = confidence
    dataframe[f"{p}range_z"] = range_z
    dataframe[f"{p}volume_percentile_frac"] = vol_pctl_frac
    dataframe[f"{p}reclaim_frac"] = reclaim_frac
    dataframe[f"{p}impulse_dir"] = impulse_dir
    dataframe[f"{p}sweep_bars_since"] = sweep_bars_since
    dataframe[f"{p}liquidity_quality"] = liquidity_quality

    return dataframe


# ════════════════════════════════════════════════════════════════
# Helper: regime routing matrix (from regime_configs.py)
# ════════════════════════════════════════════════════════════════

# Maps composite_regime → list of strategy names allowed to trade.
# This is the deterministic routing matrix from regime_configs.py,
# distilled to the strategies worth porting.
REGIME_STRATEGY_MATRIX: dict[str, list[str]] = {
    # CHOP_LOW family — vol expansion breakout sweet spot
    "CHOP_LOW_CONTRACT": ["VOL_EXPANSION_BREAKOUT"],
    "CHOP_LOW_NEUTRAL": ["VOL_EXPANSION_BREAKOUT"],
    "CHOP_LOW_EXPAND": ["VOL_EXPANSION_BREAKOUT"],
    # CHOP_HIGH — panic fade only
    "CHOP_HIGH_CONTRACT": ["VOL_EXPANSION_BREAKOUT"],
    "CHOP_HIGH_NEUTRAL": ["VOL_EXPANSION_BREAKOUT"],
    "CHOP_HIGH_EXPAND": ["PANIC_FADE_LIQ_SWEEP"],
    # TREND_UP — vol expansion; TRBK available but disabled by default
    # To enable TRBK: set buy_trbk_enabled=True AND uncomment TRBK entries below:
    "TREND_UP_CONTRACT": ["VOL_EXPANSION_BREAKOUT", "TREND_BREAKOUT_RESUMPTION"],
    "TREND_UP_NEUTRAL": ["VOL_EXPANSION_BREAKOUT", "TREND_BREAKOUT_RESUMPTION"],
    "TREND_UP_EXPAND": ["VOL_EXPANSION_BREAKOUT"],
    # DOWN family — panic fade on capitulation; no TRBK here for now
    "DOWN_LOW_CONTRACT": [],
    "DOWN_LOW_NEUTRAL": [],
    "DOWN_LOW_EXPAND": [],
    "DOWN_NORMAL_CONTRACT": ["PANIC_FADE_LIQ_SWEEP", "TREND_BREAKOUT_RESUMPTION"],
    "DOWN_NORMAL_NEUTRAL": ["PANIC_FADE_LIQ_SWEEP", "TREND_BREAKOUT_RESUMPTION"],
    "DOWN_NORMAL_EXPAND": ["PANIC_FADE_LIQ_SWEEP"],
    "DOWN_HIGH_CONTRACT": [],
    "DOWN_HIGH_NEUTRAL": [],
    "DOWN_HIGH_EXPAND": [],
    "DOWN_HIGH_CAPITULATION": ["PANIC_FADE_LIQ_SWEEP"],
}


def strategy_allowed(composite_regime: str, strategy_name: str) -> bool:
    """Check if a strategy is allowed in the current composite regime."""
    allowed = REGIME_STRATEGY_MATRIX.get(composite_regime, [])
    return strategy_name in allowed
