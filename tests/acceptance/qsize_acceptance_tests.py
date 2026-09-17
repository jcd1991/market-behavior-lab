#!/usr/bin/env python3
"""
Lightweight acceptance tests for qsize helpers.

Run:
  python tests/acceptance/qsize_acceptance_tests.py
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "user_data" / "strategies"))

from RegimeRouted import RegimeRouted  # noqa: E402


class _P:
    def __init__(self, v):
        self.value = v


class _Dummy:
    buy_volex_informative_tf = _P("4h")
    buy_qsize_w_trend = _P(0.40)
    buy_qsize_w_break = _P(0.35)
    buy_qsize_w_vol = _P(0.25)
    buy_pair_attention_enabled = _P(False)
    buy_pair_attention_mode = _P("qsize_feature")
    buy_qsize_w_attention = _P(0.20)
    buy_pair_attention_zscore_clip = _P(3.0)
    buy_qsize_ml_enabled = _P(False)
    buy_qsize_ml_profile = _P("off")
    buy_qsize_ml_blend = _P(0.0)
    buy_qsize_min_mult = _P(0.80)
    buy_qsize_max_mult = _P(1.30)
    buy_qsize_deadband = _P(0.10)
    buy_qsize_confidence_exp = _P(1.30)
    buy_qsize_upscale_min_score = _P(0.62)
    buy_qsize_riskoff_cap_enabled = _P(True)
    buy_qsize_riskoff_cap = _P(1.00)
    buy_qsize_bucket_cap_map = _P("")
    buy_qsize_short_cap = _P(1.00)
    _clip01 = staticmethod(RegimeRouted._clip01)
    _csv_kv_float_map = staticmethod(RegimeRouted._csv_kv_float_map)
    _qsize_score = RegimeRouted._qsize_score
    _qsize_mult = RegimeRouted._qsize_mult


def run_tests() -> None:
    d = _Dummy()

    score, _ = d._qsize_score(None, "cbx", "long")
    assert abs(score - 0.5) < 1e-9

    row_long = pd.Series(
        {
            "close": 105.0,
            "cbx4h_break_thr": 100.0,
            "atr14": 2.0,
            "cbx_adx": 30.0,
            "atr_phase": "EXPAND",
        }
    )
    score_long, _ = d._qsize_score(row_long, "cbx", "long")
    assert 0.60 <= score_long <= 1.0, score_long

    row_short = pd.Series(
        {
            "close": 95.0,
            "trbk_donch_high_4h": 100.0,
            "atr14": 2.0,
            "trbk_adx": 28.0,
            "atr_phase": "EXPAND",
        }
    )
    score_short, _ = d._qsize_score(row_short, "trbk", "short")
    assert 0.50 <= score_short <= 1.0, score_short

    assert abs(d._qsize_mult(0.0) - 0.80) < 1e-9
    assert abs(d._qsize_mult(1.0) - 1.30) < 1e-9
    # Neutral quality must not receive leverage-like upscaling.
    assert abs(d._qsize_mult(0.5) - 1.00) < 1e-9

    print("qsize acceptance tests: PASS")


if __name__ == "__main__":
    run_tests()
