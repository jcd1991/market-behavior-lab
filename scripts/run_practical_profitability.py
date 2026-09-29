#!/usr/bin/env python3
"""Run the ordered momentum, carry, and cross-sectional research screens."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.evaluation.cash_carry import CarryAssumptions, evaluate_pair, tune_pair
from research.evaluation.cross_sectional_portfolio import PortfolioPolicy, tune_portfolio
from research.evaluation.momentum_reconstruction import MomentumPolicy, simulate, tune


def load_candles(root: Path, pattern: str, quote: str) -> pd.DataFrame:
    rows = []
    for path in sorted(root.glob(pattern)):
        frame = pd.read_feather(path)
        base = path.name.split("_")[0]
        frame["pair"] = f"{base}/{quote}"
        frame["timestamp"] = pd.to_datetime(frame.pop("date"), utc=True, errors="coerce")
        rows.append(frame[["timestamp", "pair", "close", "volume"]])
    if not rows:
        raise FileNotFoundError(f"no candle files matched {root / pattern}")
    return pd.concat(rows, ignore_index=True)


def static_membership(candles: pd.DataFrame) -> pd.DataFrame:
    pairs = sorted(candles["pair"].dropna().unique())
    return pd.DataFrame({"effective_at": [pd.Timestamp("2025-01-01", tz="UTC")] * len(pairs), "pair": pairs})


def momentum_screen(root: Path, pattern: str, quote: str, fee_bps: float) -> dict[str, Any]:
    candles = load_candles(root, pattern, quote)
    policy = MomentumPolicy(lookback_days=14, trend_days=30, regime_days=60, top_n=2, exit_rank=9,
                            fee_bps=fee_bps, spread_bps=5.0, slippage_bps=10.0, max_pair_weight=0.50)
    return {"frozen_policy": policy.__dict__, "available": simulate(candles, policy),
            "forward_2026": simulate(candles, policy, start="2026-01-01"),
            "tuning": tune(candles, train_end="2025-01-01", holdout_start="2025-01-01")}


def cross_sectional_screen(root: Path, pattern: str, quote: str, fee_bps: float) -> dict[str, Any]:
    candles = load_candles(root, pattern, quote)
    membership = static_membership(candles)
    costs = {"fee_bps": fee_bps, "spread_bps": 5.0, "slippage_bps": 10.0}
    grid = [
        PortfolioPolicy(lookback=42, reversal_window=12, volatility_window=42, rebalance_every=6, longs=3, **costs),
        PortfolioPolicy(lookback=84, reversal_window=18, volatility_window=84, rebalance_every=12, longs=3, **costs),
        PortfolioPolicy(lookback=126, reversal_window=24, volatility_window=126, rebalance_every=24, longs=2, **costs),
        PortfolioPolicy(lookback=168, reversal_window=24, volatility_window=168, rebalance_every=42, longs=2, **costs),
    ]
    return {"membership": "static research fixture", "tuning": tune_portfolio(candles, membership,
             train_end="2026-01-01", holdout_start="2026-01-01", grid=grid)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("user_data/data"))
    parser.add_argument("--okx-root", type=Path, default=Path("user_data/data/okx"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--carry-spot", type=Path)
    parser.add_argument("--carry-perp", type=Path)
    parser.add_argument("--carry-funding", type=Path)
    parser.add_argument("--carry-index", type=Path)
    args = parser.parse_args()
    result: dict[str, Any] = {
        "momentum": {
            "binance": momentum_screen(args.data_root, "*_USDT-15m.feather", "USDT", 10.0),
            "coinbase": momentum_screen(args.data_root, "*_USD-15m.feather", "USD", 60.0),
            "okx": momentum_screen(args.okx_root, "*_USDT-15m.feather", "USDT", 10.0),
        },
        "cross_sectional": cross_sectional_screen(args.data_root, "*_USD-4h.feather", "USD", 60.0),
    }
    carry_paths = (args.carry_spot, args.carry_perp, args.carry_funding, args.carry_index)
    if all(carry_paths):
        spot, perp, funding, index = carry_paths
        result["carry"] = {"screen": evaluate_pair(spot, perp, funding, index, "binance-global", "binance-global",
                                                       assumptions=CarryAssumptions()),
                            "tuning": tune_pair(spot, perp, funding, index, "binance-global", "binance-global",
                                                 train_end="2026-08-19", holdout_start="2026-08-19")}
    else:
        result["carry"] = {"eligible": False, "reason": "carry paths not supplied"}
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
