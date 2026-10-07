#!/usr/bin/env python3
"""Run the free-data profitability matrix for the current research lanes.

The report deliberately keeps four evidence classes separate:

* Binance Global normalized derivatives data for same-venue BTC/ETH lanes;
* local Freqtrade candle files for the static cross-sectional screen;
* prior venue-labelled Freqtrade exports for the frozen trend ensemble; and
* modeled costs where measured order-book history is not available.

This is a screening harness, not a live-trading command.  It never downloads
credentials, joins venues, or promotes a positive result to execution truth.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.evaluation.cash_carry import CarryAssumptions, audit_same_venue_inputs, evaluate_frames
from research.evaluation.cointegration_book import audit_two_leg_inputs, load_ohlcv, simulate_pair
from research.evaluation.cross_sectional_portfolio import PortfolioPolicy, build_features, simulate_portfolio, tune_portfolio
from research.evaluation.derivatives_momentum import prepare_features, tune as tune_derivative_momentum
from research.evaluation.portfolio_validation import load_detailed_trades
from research.evaluation.volatility_ensemble import SleeveSpec, evaluate_frozen_sleeves


BINANCE = ROOT / "user_data/data/historical/normalized/binance-global/acquisition-2026-09-28"
LOCAL_SPOT = ROOT / "user_data/data"
EXPORTS = ROOT / "user_data/backtest_results"


def _read(path: Path) -> pd.DataFrame:
    frame = pd.read_feather(path)
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    return frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date").reset_index(drop=True)


def _clip(frame: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = frame
    if start:
        out = out[out["date"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        out = out[out["date"] < pd.Timestamp(end, tz="UTC")]
    return out.copy()


def _score(result: dict[str, Any], *, minimum_trades: int = 5) -> float:
    if not result.get("eligible") or int(result.get("accepted", result.get("entries", 0))) < minimum_trades:
        return -100000.0
    return float(result.get("profit_pct", result.get("profit_ratio", -1000.0) * 100.0)) - 0.75 * float(result.get("max_drawdown_pct", 1000.0))


def _residual_grid(asset: pd.DataFrame, reference: pd.DataFrame, *, start: str, end: str, cost: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window, entry_z, exit_z, min_corr in itertools.product((120, 240), (1.6, 2.0, 2.4), (0.25, 0.50), (0.60, 0.75)):
        result = simulate_pair(
            _clip(asset.reset_index().rename(columns={"index": "date"}), start, end).set_index("date"),
            _clip(reference.reset_index().rename(columns={"index": "date"}), start, end).set_index("date"),
            venue="binance-global",
            window=window,
            entry_z=entry_z,
            exit_z=exit_z,
            min_corr=min_corr,
            max_half_life=168.0,
            round_trip_cost=cost,
        )
        rows.append({"params": {"window": window, "entry_z": entry_z, "exit_z": exit_z, "min_corr": min_corr, "max_half_life": 168.0, "round_trip_cost": cost}, "result": result, "score": _score(result)})
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def residual_report() -> dict[str, Any]:
    asset_path = BINANCE / "BTC_USDT_USDT-1m-futures.feather"
    reference_path = BINANCE / "ETH_USDT_USDT-1m-futures.feather"
    audit = audit_two_leg_inputs(asset_path, reference_path, "binance-global", "binance-global", min_overlap_days=90)
    asset = load_ohlcv(asset_path)
    reference = load_ohlcv(reference_path)
    full = simulate_pair(asset, reference, venue="binance-global", window=240, entry_z=2.0, exit_z=0.5, min_corr=0.75, max_half_life=168.0, round_trip_cost=0.004)
    windows = [
        ("2026-06-01", "2026-07-15", "2026-07-15", "2026-08-01"),
        ("2026-06-15", "2026-08-01", "2026-08-01", "2026-09-01"),
    ]
    walk: list[dict[str, Any]] = []
    for train_start, train_end, test_start, test_end in windows:
        candidates = _residual_grid(asset, reference, start=train_start, end=train_end, cost=0.004)
        selected = candidates[0] if candidates else None
        test = simulate_pair(
            _clip(asset.reset_index().rename(columns={"index": "date"}), test_start, test_end).set_index("date"),
            _clip(reference.reset_index().rename(columns={"index": "date"}), test_start, test_end).set_index("date"),
            venue="binance-global", round_trip_cost=0.004, **{key: value for key, value in (selected["params"] if selected else {}).items() if key != "round_trip_cost"},
        ) if selected else {"eligible": False, "reason": "no_candidate"}
        walk.append({"train": {"start": train_start, "end": train_end}, "test": {"start": test_start, "end": test_end}, "selected": selected, "frozen_test": test})
    costs = {}
    for cost in (0.002, 0.004, 0.006, 0.008):
        costs[str(cost)] = simulate_pair(asset, reference, venue="binance-global", window=240, entry_z=2.0, exit_z=0.5, min_corr=0.75, max_half_life=168.0, round_trip_cost=cost)
    return {
        "lane": "two-leg residual hedge", "provenance": "binance-global-normalized-1m-futures", "contract_audit": audit,
        "full_frozen": full, "walk_forward": walk, "cost_sensitivity": costs,
        "decision": "research_only_until_positive_frozen_forward_windows_and_measured_two-leg_fills",
    }


def _load_derivative_frames() -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in ("BTC", "ETH"):
        prefix = f"{symbol}_USDT"
        candles = _read(BINANCE / f"{prefix}_USDT-1m-futures.feather")
        mark = _read(BINANCE / f"{prefix}_USDT-mark-1m.feather")
        index = _read(BINANCE / f"{prefix}_USDT-index-1m.feather")
        funding = _read(BINANCE / f"{prefix}_USDT-funding.feather")
        metrics = _read(BINANCE / f"{prefix}_USDT-metrics-5m.feather")
        if "available_at" not in metrics or metrics["available_at"].isna().any():
            raise RuntimeError(f"{metrics} lacks a complete point-in-time availability column")
        frames[f"{symbol}/USDT:USDT"] = prepare_features(candles, mark=mark, index=index, metrics=metrics, funding=funding, rule="5min")
    return frames


def derivative_momentum_report() -> dict[str, Any]:
    frames = _load_derivative_frames()
    result = tune_derivative_momentum(frames, train_start="2026-06-01", train_end="2026-07-31", holdout_start="2026-08-01", holdout_end="2026-09-01")
    result["lane"] = "derivatives-conditioned momentum"
    result["provenance"] = "binance-global-normalized-1m-futures-plus-5m-metrics"
    result["data_quality"] = {pair: {"rows": len(frame), "basis_non_null": int(frame["basis"].notna().sum()), "oi_non_null": int(frame["open_interest"].notna().sum()), "funding_non_null": int(frame["funding_rate"].notna().sum())} for pair, frame in frames.items()}
    result["decision"] = "research_only_until_metrics_alignment_and_holdout_survive_more_windows"
    return result


def carry_grid_report() -> dict[str, Any]:
    paths = {
        "spot": BINANCE / "BTC_USDT-1m.feather",
        "perp": BINANCE / "BTC_USDT_USDT-1m-futures.feather",
        "funding": BINANCE / "BTC_USDT_USDT-funding.feather",
        "index": BINANCE / "BTC_USDT_USDT-index-1m.feather",
    }
    audit = audit_same_venue_inputs(**paths, venue="binance-global", min_overlap_days=90, require_margin_buffer=True)
    frames = {name: _read(path) for name, path in paths.items()}
    train = {name: _clip(frame, "2026-06-01", "2026-07-31") for name, frame in frames.items()}
    holdout = {name: _clip(frame, "2026-08-01", "2026-09-01") for name, frame in frames.items()}
    candidates: list[dict[str, Any]] = []
    for entry_basis, exit_basis, min_funding in itertools.product((0.002, 0.005, 0.008), (0.0, 0.001, 0.002), (0.0, 0.0001)):
        assumptions = CarryAssumptions(entry_basis=entry_basis, exit_basis=exit_basis, min_funding=min_funding, round_trip_cost=0.002, require_margin_buffer=False)
        result = evaluate_frames(train["spot"], train["perp"], train["funding"], train["index"], "binance-global", assumptions=assumptions)
        candidates.append({"assumptions": assumptions.__dict__, "train": result, "score": _score({"eligible": result.get("eligible"), "accepted": result.get("entries", 0), "profit_pct": result.get("stress_profit_pct", -1000), "max_drawdown_pct": 0.0})})
    eligible_candidates = [row for row in candidates if row["train"].get("entries", 0) >= 5]
    selected = max(eligible_candidates, key=lambda row: row["score"]) if eligible_candidates else None
    frozen = (
        evaluate_frames(
            holdout["spot"], holdout["perp"], holdout["funding"], holdout["index"], "binance-global",
            assumptions=CarryAssumptions(**selected["assumptions"]),
        )
        if selected else {"eligible": False, "reason": "no_train_candidate_with_minimum_five_entries"}
    )
    cost_sensitivity = {}
    for cost in (0.001, 0.002, 0.004, 0.006):
        assumptions = CarryAssumptions(**{**(selected["assumptions"] if selected else candidates[0]["assumptions"]), "round_trip_cost": cost})
        cost_sensitivity[str(cost)] = evaluate_frames(frames["spot"], frames["perp"], frames["funding"], frames["index"], "binance-global", assumptions=assumptions)
    return {
        "lane": "same-venue cash-and-carry", "provenance": "binance-global-normalized-spot-perp-index-funding", "contract_audit": audit,
        "strict_promotion_block": "margin_buffer_missing" in audit.get("failures", []), "selected": selected["assumptions"] if selected else None,
        "selection_rule": "train stress profit with modeled costs; margin buffer remains disabled because historical observations are absent",
        "train_candidates_with_minimum_five_entries": len(eligible_candidates), "train_top5": sorted(candidates, key=lambda row: row["score"], reverse=True)[:5], "frozen_holdout": frozen,
        "full_cost_sensitivity": cost_sensitivity, "decision": "diagnostic_only_until_observed_margin_borrow_and_failure_data_exists",
    }


def _cross_sectional_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    pairs = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "DOGE/USDT")
    frames: list[pd.DataFrame] = []
    membership_rows: list[dict[str, str]] = []
    for pair in pairs:
        path = LOCAL_SPOT / f"{pair.replace('/', '_')}-1h.feather"
        frame = _read(path).rename(columns={"date": "timestamp"})
        frame["pair"] = pair
        frames.append(frame[["timestamp", "pair", "close", "volume"]])
        membership_rows.append({"pair": pair, "effective_at": "2024-01-01T00:00:00Z"})
    return pd.concat(frames, ignore_index=True), pd.DataFrame(membership_rows)


def cross_sectional_report() -> dict[str, Any]:
    candles, membership = _cross_sectional_inputs()
    default_policy = PortfolioPolicy(lookback=72, reversal_window=12, volatility_window=48, rebalance_every=6, longs=3, shorts=0)
    full = simulate_portfolio(build_features(candles, membership, policy=default_policy), policy=default_policy, spot_only=True)
    tuned = tune_portfolio(candles, membership, train_end="2025-01-01", holdout_start="2025-01-01", spot_only=True)
    selected_policy = PortfolioPolicy(**tuned["selected"])
    tuned["selected_full_window"] = simulate_portfolio(build_features(candles, membership, policy=selected_policy), policy=selected_policy, spot_only=True)
    return {
        "lane": "cross-sectional crypto portfolio", "provenance": "local-freqtrade-spot-candles; venue labels inherited and not re-verified in this pass",
        "universe": sorted(candles["pair"].unique()), "timeframe": "1h", "full_default": full, "tuning": tuned,
        "decision": "research_screen_only_until_point_in_time_membership_and_venue_cost_provenance_are_reverified",
    }


def _load_export_panel() -> pd.DataFrame:
    selections = {
        "volatility_trend_cash": EXPORTS / "backtest-result-2026-09-26_00-19-10.zip",
        "standalone_breakout": EXPORTS / "backtest-result-2026-09-25_20-07-07.zip",
        "multi_timeframe_confirmation": EXPORTS / "backtest-result-2026-09-19_19-07-09.zip",
    }
    frames: list[pd.DataFrame] = []
    for lane, path in selections.items():
        frame = load_detailed_trades(path, lane).rename(columns={"open_date": "open_time", "close_date": "close_time"})
        frame["sleeve"] = lane
        frames.append(frame[["sleeve", "pair", "open_time", "close_time", "profit_ratio"]])
    return pd.concat(frames, ignore_index=True)


def ensemble_report() -> dict[str, Any]:
    trades = _load_export_panel()
    all_names = sorted(trades["sleeve"].unique())
    specs = tuple(SleeveSpec(name=name, weight=1.0 / len(all_names), max_pair_fraction=0.25) for name in all_names)
    shared = evaluate_frozen_sleeves(trades, specs, starting_balance=1000.0, max_open_positions=3, fee_bps=0.0, spread_bps=5.0, slippage_bps=5.0)
    positive_names = ["standalone_breakout", "volatility_trend_cash"]
    positive_trades = trades[trades["sleeve"].isin(positive_names)].copy()
    positive_specs = tuple(SleeveSpec(name=name, weight=0.5, max_pair_fraction=0.25) for name in positive_names)
    shared_positive = evaluate_frozen_sleeves(positive_trades, positive_specs, starting_balance=1000.0, max_open_positions=3, fee_bps=0.0, spread_bps=5.0, slippage_bps=5.0)
    train_cut = pd.Timestamp("2025-01-01", tz="UTC")
    train_trades = positive_trades[positive_trades["close_time"] < train_cut]
    holdout_trades = positive_trades[positive_trades["close_time"] >= train_cut]
    candidates = []
    for breakout_weight, max_open, pair_cap in itertools.product((0.25, 0.50, 0.75), (2, 3, 4), (0.25, 0.40)):
        specs_candidate = (
            SleeveSpec("standalone_breakout", breakout_weight, pair_cap),
            SleeveSpec("volatility_trend_cash", 1.0 - breakout_weight, pair_cap),
        )
        train_result = evaluate_frozen_sleeves(train_trades, specs_candidate, starting_balance=1000.0, max_open_positions=max_open, fee_bps=0.0, spread_bps=5.0, slippage_bps=5.0)
        candidates.append({"breakout_weight": breakout_weight, "max_open_positions": max_open, "pair_cap": pair_cap, "train": train_result, "score": float(train_result.get("profit_pct", -1000.0)) - 0.75 * float(train_result.get("max_drawdown_pct", 1000.0))})
    selected = max(candidates, key=lambda row: row["score"])
    selected_specs = (
        SleeveSpec("standalone_breakout", selected["breakout_weight"], selected["pair_cap"]),
        SleeveSpec("volatility_trend_cash", 1.0 - selected["breakout_weight"], selected["pair_cap"]),
    )
    tuned_holdout = evaluate_frozen_sleeves(holdout_trades, selected_specs, starting_balance=1000.0, max_open_positions=selected["max_open_positions"], fee_bps=0.0, spread_bps=5.0, slippage_bps=5.0)
    individual = {}
    for spec in specs:
        individual[spec.name] = evaluate_frozen_sleeves(trades[trades["sleeve"] == spec.name], (SleeveSpec(spec.name, 1.0),), starting_balance=1000.0, max_open_positions=3, fee_bps=0.0, spread_bps=5.0, slippage_bps=5.0)
    return {
        "lane": "volatility-managed trend ensemble plus shared wallet", "provenance": "prior Binance.US-labelled Freqtrade exports; original venue files not re-run here",
        "cost_note": "Freqtrade exports already include configured fees; this replay adds 5 bps spread plus 5 bps slippage round trip and no second fee charge",
        "individual": individual, "shared_wallet_all_three": shared, "shared_wallet_breakout_plus_volatility": shared_positive,
        "tuning": {"train_end": "2025-01-01", "selected": selected, "holdout": tuned_holdout, "selection_rule": "train profit minus 0.75x drawdown; frozen positive-sleeve holdout"},
        "decision": "screening_evidence_only_until_synchronized_signal_and_fill_replay",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "research/reports/generated/free-profitability-matrix-2026-10-07.json")
    args = parser.parse_args()
    report = {
        "schema_version": "free-profitability-matrix.v1", "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "research_scope": "six requested free-data lanes", "costs_are_modeled_unless_explicitly_noted": True,
        "residual_hedge": residual_report(),
        "derivatives_momentum": derivative_momentum_report(),
        "cash_carry": carry_grid_report(),
        "cross_sectional": cross_sectional_report(),
        "volatility_ensemble": ensemble_report(),
        "overall_decision": "no_lane_is_promoted; prioritize frozen forward survival, measured fills, and data provenance over more tuning",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "residual_full_pct": report["residual_hedge"]["full_frozen"].get("profit_pct"),
        "derivatives_holdout_pct": report["derivatives_momentum"].get("holdout_result", {}).get("profit_pct"),
        "carry_holdout_pct": report["cash_carry"]["frozen_holdout"].get("profit_pct"),
        "cross_sectional_holdout_pct": report["cross_sectional"]["tuning"]["holdout"].get("profit_pct"),
        "ensemble_all_three_pct": report["volatility_ensemble"]["shared_wallet_all_three"].get("profit_pct"),
        "ensemble_breakout_plus_volatility_pct": report["volatility_ensemble"]["shared_wallet_breakout_plus_volatility"].get("profit_pct"),
        "ensemble_tuned_holdout_pct": report["volatility_ensemble"]["tuning"]["holdout"].get("profit_pct"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
