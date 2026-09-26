"""Concentration, forward, and synchronized-execution validation helpers.

This module is a gate around historical Freqtrade exports.  It does not infer
missing fills, convert one venue into another, or promote a positive screen to
an execution claim.  The bootstrap results are diagnostic uncertainty bands,
not statistical guarantees.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.evaluation.synergistic_matrix import MatrixCandidate, simulate_shared_wallet


def load_detailed_trades(path: Path, lane: str | None = None) -> pd.DataFrame:
    """Load the trade-level fields needed for concentration analysis."""

    from research.evaluation.synergistic_matrix import load_result

    result = load_result(path)
    name = lane or str(result.get("strategy_name") or path.stem)
    rows: list[dict[str, Any]] = []
    for index, trade in enumerate(result.get("trades", [])):
        opened = pd.to_datetime(trade.get("open_date"), utc=True, errors="coerce")
        closed = pd.to_datetime(trade.get("close_date"), utc=True, errors="coerce")
        if pd.isna(opened) or pd.isna(closed):
            continue
        ratio = trade.get("profit_ratio")
        if ratio is None:
            ratio = float(trade.get("profit_pct", 0.0) or 0.0) / 100.0
        profit_abs = trade.get("profit_abs")
        if profit_abs is None:
            profit_abs = float(trade.get("stake_amount", 0.0) or 0.0) * float(ratio or 0.0)
        rows.append(
            {
                "trade_id": index,
                "lane": name,
                "pair": str(trade.get("pair", "")),
                "open_date": opened,
                "close_date": closed,
                "profit_ratio": float(ratio or 0.0),
                "profit_abs": float(profit_abs or 0.0),
                "stake_amount": float(trade.get("stake_amount", 0.0) or 0.0),
                "enter_tag": str(trade.get("enter_tag", "")),
                "exit_reason": str(trade.get("exit_reason", "")),
            }
        )
    return pd.DataFrame(rows)


def _path_stats(profits: np.ndarray, starting_balance: float) -> tuple[float, float]:
    equity = starting_balance + np.cumsum(profits)
    if equity.size == 0:
        return 0.0, 0.0
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    return float((equity[-1] / starting_balance - 1.0) * 100.0), float(-drawdown.min() * 100.0)


def concentration_report(trades: pd.DataFrame, *, starting_balance: float = 1000.0) -> dict[str, Any]:
    """Measure dependence on a few trades, pairs, and calendar months."""

    if trades.empty:
        return {"eligible": False, "reason": "empty_trade_set"}
    profits = trades["profit_abs"].to_numpy(dtype=float)
    positive = np.maximum(profits, 0.0)
    positive_total = float(positive.sum())
    ordered = np.sort(positive)[::-1]
    pair_profit = trades.groupby("pair", dropna=False)["profit_abs"].sum().sort_values(ascending=False)
    pair_positive = trades.assign(_positive=positive).groupby("pair", dropna=False)["_positive"].sum().sort_values(ascending=False)
    pair_positive_total = float(pair_positive.sum())
    month_profit = trades.assign(month=trades["open_date"].dt.strftime("%Y-%m")).groupby("month")["profit_abs"].sum()
    return {
        "eligible": True,
        "trade_count": int(len(trades)),
        "pair_count": int(trades["pair"].nunique()),
        "month_count": int(month_profit.size),
        "profit_abs": float(profits.sum()),
        "profit_pct": float(profits.sum() / starting_balance * 100.0),
        "winning_trades": int((profits > 0).sum()),
        "losing_trades": int((profits < 0).sum()),
        "top_trade_profit_abs": float(ordered[0]) if ordered.size else 0.0,
        "top_trade_share_of_gains": float(ordered[0] / positive_total) if positive_total else 0.0,
        "top_three_share_of_gains": float(ordered[:3].sum() / positive_total) if positive_total else 0.0,
        "profit_without_top_trade_pct": float((profits.sum() - (ordered[0] if ordered.size else 0.0)) / starting_balance * 100.0),
        "profit_without_top_three_pct": float((profits.sum() - ordered[:3].sum()) / starting_balance * 100.0),
        "largest_loss_abs": float(profits.min()),
        "best_pair": str(pair_profit.index[0]) if not pair_profit.empty else None,
        "best_pair_profit_abs": float(pair_profit.iloc[0]) if not pair_profit.empty else 0.0,
        "top_pair_share_of_gains": float(pair_positive.iloc[0] / pair_positive_total) if pair_positive_total else 0.0,
        "pair_positive_gain_shares": {
            str(pair): float(value / pair_positive_total) if pair_positive_total else 0.0
            for pair, value in pair_positive.items()
        },
        "monthly_profit_abs": {str(month): float(value) for month, value in month_profit.items()},
    }


def bootstrap_report(
    trades: pd.DataFrame,
    *,
    starting_balance: float = 1000.0,
    iterations: int = 5000,
    seed: int = 20260926,
) -> dict[str, Any]:
    """Run trade and month-block bootstrap diagnostics with a fixed seed."""

    if trades.empty:
        return {"eligible": False, "reason": "empty_trade_set"}
    rng = np.random.default_rng(seed)
    profits = trades["profit_abs"].to_numpy(dtype=float)
    trade_paths = rng.choice(profits, size=(iterations, len(profits)), replace=True)
    trade_returns = (starting_balance + trade_paths.sum(axis=1)) / starting_balance - 1.0
    trade_equity = starting_balance + np.cumsum(trade_paths, axis=1)
    trade_dd = 1.0 - trade_equity / np.maximum.accumulate(trade_equity, axis=1)

    work = trades.assign(month=trades["open_date"].dt.strftime("%Y-%m"))
    month_groups = [group["profit_abs"].to_numpy(dtype=float) for _, group in work.groupby("month", sort=True)]
    month_paths: list[np.ndarray] = []
    if month_groups:
        for _ in range(iterations):
            chosen = rng.integers(0, len(month_groups), size=len(month_groups))
            month_paths.append(np.concatenate([month_groups[index] for index in chosen]))
    month_returns = np.array([(starting_balance + path.sum()) / starting_balance - 1.0 for path in month_paths])

    def quantiles(values: np.ndarray) -> dict[str, float]:
        return {key: float(value * 100.0) for key, value in zip(("p05", "p50", "p95"), np.quantile(values, [0.05, 0.50, 0.95]))}

    return {
        "eligible": True,
        "iterations": iterations,
        "seed": seed,
        "trade_bootstrap": {
            "profit_pct": quantiles(trade_returns),
            "probability_positive_pct": float((trade_returns > 0.0).mean() * 100.0),
            "max_drawdown_pct_p95": float(np.quantile(trade_dd.max(axis=1), 0.95) * 100.0),
        },
        "month_block_bootstrap": {
            "months": len(month_groups),
            "profit_pct": quantiles(month_returns) if month_returns.size else {},
            "probability_positive_pct": float((month_returns > 0.0).mean() * 100.0) if month_returns.size else 0.0,
        },
        "warning": "resampling historical trades is a dependence diagnostic, not a forecast or confidence guarantee",
    }


def replay_order_sensitivity(
    candidates: list[MatrixCandidate],
    weights: dict[str, float],
    *,
    starting_balance: float = 1000.0,
    max_open: int = 3,
    pair_cap: float = 0.40,
    extra_round_trip_cost: float = 0.002,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Replay all sleeve-priority permutations through one shared wallet."""

    if len(candidates) > 6:
        raise ValueError("order sensitivity is capped at six sleeves")
    rows: list[dict[str, Any]] = []
    for order in itertools.permutations(candidates):
        result = simulate_shared_wallet(
            list(order),
            weights,
            starting_balance=starting_balance,
            max_open=max_open,
            pair_cap=pair_cap,
            extra_round_trip_cost=extra_round_trip_cost,
            start=start,
            end=end,
        )
        rows.append(
            {
                "order": [candidate.name for candidate in order],
                "eligible": result.get("eligible", False),
                "profit_pct": result.get("profit_pct"),
                "max_drawdown_pct": result.get("max_drawdown_pct"),
                "accepted": result.get("accepted"),
                "rejected": result.get("rejected"),
                "rejections": result.get("rejections", {}),
            }
        )
    eligible = [row for row in rows if row["eligible"]]
    profits = np.array([float(row["profit_pct"]) for row in eligible], dtype=float)
    return {
        "eligible": bool(eligible),
        "permutations": len(rows),
        "profit_pct": {
            "min": float(profits.min()) if profits.size else None,
            "max": float(profits.max()) if profits.size else None,
            "median": float(np.median(profits)) if profits.size else None,
        },
        "max_drawdown_pct": {
            "min": float(min(row["max_drawdown_pct"] for row in eligible)) if eligible else None,
            "max": float(max(row["max_drawdown_pct"] for row in eligible)) if eligible else None,
        },
        "all_orders_positive": bool(profits.size and np.all(profits > 0.0)),
        "rows": rows,
        "method": "same-venue trade-export replay; close events precede new opens; priority is the only randomized dimension",
    }


def build_validation_report(
    *,
    primary: Path,
    forward: Path,
    crash: Path,
    data_root: Path,
    primary_start: str,
    primary_end: str,
    holdout_start: str = "2025-01-01",
    holdout_end: str = "2025-12-02",
    forward_start: str,
    forward_end: str,
    third_venue_name: str = "okx",
    third_venue_status: str = "blocked",
    third_venue_reason: str = "exact winner export or source is unavailable for this venue",
    iterations: int = 5000,
) -> dict[str, Any]:
    primary_trades = load_detailed_trades(primary, "momentum")
    forward_trades = load_detailed_trades(forward, "momentum_forward")
    primary_candidate = MatrixCandidate("momentum", primary, venue="binanceus", market_type="spot", timeframe="15m")
    crash_candidate = MatrixCandidate("crash", crash, venue="binanceus", market_type="spot", timeframe="4h")
    synchronized = simulate_shared_wallet(
        [primary_candidate, crash_candidate],
        {"momentum": 0.70, "crash": 0.30},
        data_root=data_root,
        starting_balance=1000.0,
        max_open=3,
        pair_cap=0.40,
        extra_round_trip_cost=0.002,
        start=primary_start,
        end=primary_end,
    )
    synchronized_holdout = simulate_shared_wallet(
        [primary_candidate, crash_candidate],
        {"momentum": 0.70, "crash": 0.30},
        data_root=data_root,
        starting_balance=1000.0,
        max_open=3,
        pair_cap=0.40,
        extra_round_trip_cost=0.002,
        start=holdout_start,
        end=holdout_end,
    )
    order_sensitivity = replay_order_sensitivity(
        [primary_candidate, crash_candidate],
        {"momentum": 0.70, "crash": 0.30},
        start=primary_start,
        end=primary_end,
    )
    gates = [
        {
            "gate": "synchronized_shared_wallet",
            "status": "pass" if synchronized.get("eligible") and synchronized.get("profit_pct", 0.0) > 0.0 else "fail",
            "result": {key: synchronized.get(key) for key in ("profit_pct", "max_drawdown_pct", "accepted", "rejected", "rejections")},
        },
        {
            "gate": "locked_2025_holdout",
            "status": "pass" if synchronized_holdout.get("eligible") and synchronized_holdout.get("profit_pct", 0.0) > 0.0 else "fail",
            "result": {key: synchronized_holdout.get(key) for key in ("profit_pct", "max_drawdown_pct", "accepted", "rejected", "rejections")},
        },
        {
            "gate": "sleeve_priority_sensitivity",
            "status": "pass" if order_sensitivity.get("all_orders_positive") else "review",
            "result": order_sensitivity["profit_pct"],
        },
        {
            "gate": "2026_forward",
            "status": "review" if len(forward_trades) < 30 else ("pass" if forward_trades["profit_abs"].sum() > 0 else "fail"),
            "reason": "forward export is venue-matched but has fewer than 30 trades" if len(forward_trades) < 30 else None,
            "result": concentration_report(forward_trades),
        },
        {
            "gate": "third_venue",
            "status": third_venue_status,
            "venue": third_venue_name,
            "reason": third_venue_reason,
        },
    ]
    return {
        "schema_version": "portfolio-validation-gate.v1",
        "lead": "MomentumRegimeBasket15mLb30 plus BreakoutCrashStateSpot",
        "primary_window": {"start": primary_start, "end": primary_end, "venue": "binanceus-labelled", "market_type": "spot"},
        "locked_holdout_window": {"start": holdout_start, "end": holdout_end, "venue": "binanceus-labelled", "market_type": "spot"},
        "forward_window": {"start": forward_start, "end": forward_end, "venue": "coinbase", "market_type": "spot"},
        "concentration": {
            "primary": concentration_report(primary_trades),
            "forward": concentration_report(forward_trades),
        },
        "monte_carlo": {
            "primary": bootstrap_report(primary_trades, iterations=iterations),
            "forward": bootstrap_report(forward_trades, iterations=iterations),
        },
        "synchronized_execution": synchronized,
        "synchronized_execution_holdout": synchronized_holdout,
        "sleeve_priority_sensitivity": order_sensitivity,
        "gates": gates,
        "decision": "credible_portfolio_research_lead_only_if_all_gates_pass; current report is not a promotion",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--forward", type=Path, required=True)
    parser.add_argument("--crash", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--primary-start", required=True)
    parser.add_argument("--primary-end", required=True)
    parser.add_argument("--holdout-start", default="2025-01-01")
    parser.add_argument("--holdout-end", default="2025-12-02")
    parser.add_argument("--forward-start", required=True)
    parser.add_argument("--forward-end", required=True)
    parser.add_argument("--third-venue-name", default="okx")
    parser.add_argument("--third-venue-status", default="blocked")
    parser.add_argument("--third-venue-reason", default="exact winner export or source is unavailable for this venue")
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build_validation_report(
        primary=args.primary,
        forward=args.forward,
        crash=args.crash,
        data_root=args.data_root,
        primary_start=args.primary_start,
        primary_end=args.primary_end,
        holdout_start=args.holdout_start,
        holdout_end=args.holdout_end,
        forward_start=args.forward_start,
        forward_end=args.forward_end,
        third_venue_name=args.third_venue_name,
        third_venue_status=args.third_venue_status,
        third_venue_reason=args.third_venue_reason,
        iterations=args.iterations,
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
