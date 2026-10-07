#!/usr/bin/env python3
"""Run the frozen OKX portability gate for the two surviving research lanes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.evaluation.cross_sectional_portfolio import PortfolioPolicy
from research.evaluation.portability import (
    build_data_quality_report,
    equal_weight_buy_hold,
    evaluate_breakout_volatility,
    evaluate_cross_sectional,
    load_okx_spot,
    resample_ohlcv,
)


def _resampled(candles: dict[str, pd.DataFrame], rule: str) -> dict[str, pd.DataFrame]:
    return {pair: resample_ohlcv(frame, rule) for pair, frame in candles.items()}


def _cross_sectional_cost_sensitivity(candles: dict[str, pd.DataFrame], policy: PortfolioPolicy) -> dict[str, dict]:
    rows = {}
    for fee, spread, slippage in ((10.0, 5.0, 5.0), (15.0, 10.0, 10.0), (20.0, 20.0, 20.0)):
        key = f"fee{fee:g}_spread{spread:g}_slippage{slippage:g}"
        cost_policy = PortfolioPolicy(**{**policy.__dict__, "fee_bps": fee, "spread_bps": spread, "slippage_bps": slippage})
        rows[key] = evaluate_cross_sectional(
            candles,
            policy=cost_policy,
            costs={"fee_bps_per_side": fee, "spread_bps_round_trip": spread, "slippage_bps_round_trip": slippage, "note": "modeled"},
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "user_data/data/okx")
    parser.add_argument("--output", type=Path, default=ROOT / "research/reports/generated/portability-gate-2026-10-07.json")
    parser.add_argument("--capture-manifest", type=Path, default=ROOT / "user_data/data/microstructure/raw/okx/spot/20260925T040931Z-f157448b/manifest.json")
    args = parser.parse_args()

    native = load_okx_spot(args.data_dir)
    candles_1h = _resampled(native, "1h")
    candles_4h = _resampled(native, "4h")
    policy = PortfolioPolicy(
        lookback=168,
        reversal_window=24,
        volatility_window=168,
        rebalance_every=42,
        longs=2,
        shorts=0,
        target_vol=0.30,
        max_pair_weight=0.25,
        max_abs_beta=0.35,
        fee_bps=10.0,
        spread_bps=5.0,
        slippage_bps=5.0,
    )
    report = {
        "schema_version": "portability-gate.v1",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "scope": "frozen cross-sectional portfolio and slow breakout plus volatility-managed trend on native OKX spot data",
        "data_quality": build_data_quality_report(args.data_dir, capture_manifest=args.capture_manifest),
        "buy_and_hold_reference": equal_weight_buy_hold(candles_1h),
        "cross_sectional": {
            "frozen_policy": evaluate_cross_sectional(candles_1h, policy=policy),
            "cost_sensitivity": _cross_sectional_cost_sensitivity(candles_1h, policy),
        },
        "breakout_volatility": {
            "base_cost_case": evaluate_breakout_volatility(candles_1h, candles_4h),
            "cost_sensitivity": {
                f"fee{fee:g}_spread{spread:g}_slippage{slippage:g}": evaluate_breakout_volatility(
                    candles_1h, candles_4h, fee_bps=fee, spread_bps=spread, slippage_bps=slippage
                )
                for fee, spread, slippage in ((10.0, 5.0, 5.0), (15.0, 10.0, 10.0), (20.0, 20.0, 20.0))
            },
        },
        "promotion_gate": {
            "frozen_parameters": True,
            "tuned_on_okx": False,
            "same_venue_trade_level_fills": False,
            "synchronized_ohlcv_only": True,
            "point_in_time_universe": False,
            "decision": "portable_screen_only; do not promote to live or execution-grade profitability",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    cross = report["cross_sectional"]["frozen_policy"]
    combo = report["breakout_volatility"]["base_cost_case"]["shared_wallet_full"]
    forward = report["breakout_volatility"]["base_cost_case"]["shared_wallet_forward"]
    print(json.dumps({
        "output": str(args.output),
        "okx_pairs": report["data_quality"]["pairs"],
        "cross_sectional_full_pct": cross.get("profit_pct"),
        "cross_sectional_forward_pct": cross.get("windows", {}).get("forward", {}).get("profit_pct"),
        "breakout_volatility_full_pct": combo.get("profit_pct"),
        "breakout_volatility_forward_pct": forward.get("profit_pct"),
        "breakout_volatility_trades": report["breakout_volatility"]["base_cost_case"]["trade_counts"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
