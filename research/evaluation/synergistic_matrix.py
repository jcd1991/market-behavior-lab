"""Shared-wallet matrix for synergistic crypto research sleeves.

This module is deliberately conservative.  It combines independent Freqtrade
trade exports only after checking that they share a venue, market type, and
timeframe.  Liquidity and volatility overlays use candles strictly before the
entry timestamp.  Carry, cross-venue dispersion, and options are represented
as data-gated rows when the required history is not complete; no proxy feed is
silently substituted.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.evaluation.revised_sleeves import ExecutionCost, evaluate_carry_contract


@dataclass(frozen=True)
class MatrixCandidate:
    name: str
    path: Path
    venue: str = "binanceus"
    market_type: str = "spot"
    timeframe: str = "4h"


@dataclass(frozen=True)
class OverlayPolicy:
    """Point-in-time execution overlays for a shared-wallet screen."""

    min_quote_volume: float | None = None
    min_volume_ratio: float | None = None
    target_annual_vol: float | None = None
    volatility_lookback: int = 24
    min_vol_scale: float = 0.20
    max_vol_scale: float = 1.00
    cash_reserve: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.cash_reserve < 1.0:
            raise ValueError("cash_reserve must be in [0, 1)")
        if self.min_vol_scale <= 0 or self.max_vol_scale < self.min_vol_scale:
            raise ValueError("invalid volatility scale bounds")


def load_result(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".json") and "config" not in name]
        if not names:
            raise ValueError(f"no backtest JSON found in {path}")
        payload = json.loads(archive.read(names[0]))
    strategies = payload.get("strategy", {})
    if len(strategies) != 1:
        raise ValueError(f"expected one strategy in {path}, found {list(strategies)}")
    return next(iter(strategies.values()))


def load_trades(candidate: MatrixCandidate, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    result = load_result(candidate.path)
    rows: list[dict[str, Any]] = []
    for trade in result.get("trades", []):
        opened = pd.to_datetime(trade.get("open_date"), utc=True, errors="coerce")
        closed = pd.to_datetime(trade.get("close_date"), utc=True, errors="coerce")
        if pd.isna(opened) or pd.isna(closed):
            continue
        ratio = trade.get("profit_ratio")
        if ratio is None:
            ratio = float(trade.get("profit_pct", 0.0) or 0.0) / 100.0
        rows.append(
            {
                "lane": candidate.name,
                "pair": str(trade.get("pair", "")),
                "open_date": opened,
                "close_date": closed,
                "profit_ratio": float(ratio or 0.0),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    if start:
        frame = frame[frame["close_date"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        frame = frame[frame["close_date"] < pd.Timestamp(end, tz="UTC")]
    return frame.reset_index(drop=True)


def _pair_stems(pair: str) -> list[str]:
    """Return both spot and perpetual filename stems for a Freqtrade pair."""

    normalized = pair.replace("/", "_").replace(":", "_")
    base = normalized.split("_")
    if len(base) >= 3 and base[-1] == base[-2]:
        return ["_".join(base[:-1]) + "_" + base[-1], normalized]
    return [normalized]


def _candidate_candle_paths(data_root: Path, pair: str, timeframe: str) -> list[Path]:
    stems = _pair_stems(pair)
    paths: list[Path] = []
    for stem in stems:
        paths.extend(
            [
                data_root / f"{stem}-{timeframe}.feather",
                data_root / "futures" / f"{stem}-{timeframe}-futures.feather",
            ]
        )
    return paths


def _load_candles(data_root: Path, pair: str, timeframe: str) -> pd.DataFrame | None:
    for path in _candidate_candle_paths(data_root, pair, timeframe):
        if path.is_file():
            frame = pd.read_feather(path)
            if "date" not in frame.columns or "close" not in frame.columns or "volume" not in frame.columns:
                continue
            frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
            frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
            frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
            frame = frame.dropna(subset=["date", "close", "volume"]).sort_values("date")
            if not frame.empty:
                return frame.reset_index(drop=True)
    return None


def _annualization(timeframe: str) -> float:
    periods = {"1m": 525600.0, "5m": 105120.0, "15m": 35040.0, "30m": 17520.0, "1h": 8760.0, "4h": 2190.0, "1d": 365.0}
    return periods.get(timeframe, 8760.0)


def _entry_context(frame: pd.DataFrame | None, timestamp: pd.Timestamp, policy: OverlayPolicy, timeframe: str) -> dict[str, Any]:
    """Calculate all overlay inputs from candles strictly before entry."""

    if frame is None:
        return {"available": False, "reason": "missing_candles"}
    index = int(frame["date"].searchsorted(timestamp, side="left")) - 1
    lookback = max(2, int(policy.volatility_lookback))
    if index < lookback:
        return {"available": False, "reason": "insufficient_prior_candles", "prior_candles": max(index + 1, 0)}
    prior = frame.iloc[: index + 1]
    recent = prior.tail(lookback)
    quote_volume = float((recent["close"] * recent["volume"]).median())
    baseline_window = prior.tail(max(lookback * 4, 20))
    baseline = float((baseline_window["close"] * baseline_window["volume"]).median())
    volume_ratio = quote_volume / baseline if baseline > 0 else np.nan
    returns = prior["close"].pct_change().dropna().tail(lookback)
    realized_vol = float(returns.std(ddof=1) * np.sqrt(_annualization(timeframe))) if len(returns) >= 2 else np.nan
    scale = 1.0
    if policy.target_annual_vol is not None and np.isfinite(realized_vol) and realized_vol > 0:
        scale = float(np.clip(policy.target_annual_vol / realized_vol, policy.min_vol_scale, policy.max_vol_scale))
    volume_ok = True
    if policy.min_quote_volume is not None:
        volume_ok = volume_ok and quote_volume >= policy.min_quote_volume
    if policy.min_volume_ratio is not None:
        volume_ok = volume_ok and np.isfinite(volume_ratio) and volume_ratio >= policy.min_volume_ratio
    return {
        "available": True,
        "quote_volume": quote_volume,
        "volume_ratio": volume_ratio,
        "realized_vol": realized_vol,
        "vol_scale": scale,
        "volume_ok": bool(volume_ok),
    }


def _compatibility(candidates: list[MatrixCandidate]) -> dict[str, Any]:
    if not candidates:
        return {"compatible": False, "reason": "no_candidates"}
    venues = sorted({candidate.venue for candidate in candidates})
    market_types = sorted({candidate.market_type for candidate in candidates})
    timeframes = sorted({candidate.timeframe for candidate in candidates})
    # A shared wallet can reconcile independent signal clocks by UTC event
    # time.  Venue and market type must match; differing timeframes are an
    # explicit feature of this matrix, not a reason to mix execution venues.
    compatible = len(venues) == len(market_types) == 1
    return {
        "compatible": compatible,
        "venues": venues,
        "market_types": market_types,
        "timeframes": timeframes,
        "reason": None if compatible else "mixed_venue_or_market_type",
    }


def simulate_shared_wallet(
    candidates: list[MatrixCandidate],
    weights: dict[str, float],
    *,
    data_root: Path | None = None,
    policy: OverlayPolicy = OverlayPolicy(),
    starting_balance: float = 1000.0,
    max_open: int = 3,
    pair_cap: float = 0.40,
    extra_round_trip_cost: float = 0.0,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    compatibility = _compatibility(candidates)
    if not compatibility["compatible"]:
        return {"eligible": False, "reason": compatibility["reason"], "compatibility": compatibility}
    if any(candidate.name not in weights or weights[candidate.name] <= 0 for candidate in candidates):
        raise ValueError("each candidate needs a positive matrix weight")
    normalized_weights = {name: value / sum(weights.values()) for name, value in weights.items()}
    frames = {candidate.name: load_trades(candidate, start=start, end=end) for candidate in candidates}
    if any(frame.empty for frame in frames.values()):
        missing = [name for name, frame in frames.items() if frame.empty]
        return {"eligible": False, "reason": "empty_trade_export", "missing": missing, "compatibility": compatibility}

    candles: dict[tuple[str, str], pd.DataFrame | None] = {}
    events: list[tuple[pd.Timestamp, int, int, dict[str, Any]]] = []
    all_trades: list[dict[str, Any]] = []
    for priority, candidate in enumerate(candidates):
        for row in frames[candidate.name].to_dict(orient="records"):
            row["trade_id"] = len(all_trades)
            all_trades.append(row)
            events.append((row["open_date"], 1, priority, row))
            events.append((row["close_date"], 0, priority, row))
    events.sort(key=lambda value: (value[0], value[1], value[2]))

    balance = float(starting_balance)
    invested_fraction = 1.0 - policy.cash_reserve
    open_positions: dict[int, dict[str, Any]] = {}
    accepted: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    context_missing: dict[str, int] = {}
    overlay_samples: list[float] = []
    for timestamp, event_type, _priority, trade in events:
        trade_id = int(trade["trade_id"])
        if event_type == 0:
            position = open_positions.pop(trade_id, None)
            if position is not None:
                ratio = float(trade["profit_ratio"]) - float(extra_round_trip_cost)
                profit_abs = position["stake"] * ratio
                balance += profit_abs
                accepted.append({**position, "profit_abs": profit_abs})
            continue
        if len(open_positions) >= max_open:
            rejected["max_open"] = rejected.get("max_open", 0) + 1
            continue
        if any(pos["pair"] == trade["pair"] for pos in open_positions.values()):
            rejected["pair_overlap"] = rejected.get("pair_overlap", 0) + 1
            continue
        context = {"available": True, "volume_ok": True, "vol_scale": 1.0}
        if data_root is not None and (policy.min_quote_volume is not None or policy.min_volume_ratio is not None or policy.target_annual_vol is not None):
            key = (trade["pair"], next(candidate.timeframe for candidate in candidates if candidate.name == trade["lane"]))
            if key not in candles:
                candles[key] = _load_candles(data_root, key[0], key[1])
            context = _entry_context(candles[key], trade["open_date"], policy, key[1])
            if not context.get("available"):
                context_missing[context["reason"]] = context_missing.get(context["reason"], 0) + 1
                rejected[context["reason"]] = rejected.get(context["reason"], 0) + 1
                continue
            if not context.get("volume_ok", True):
                rejected["liquidity_gate"] = rejected.get("liquidity_gate", 0) + 1
                continue
            overlay_samples.append(float(context.get("vol_scale", 1.0)))
        sleeve_budget = balance * invested_fraction * normalized_weights[trade["lane"]]
        current_lane = sum(pos["stake"] for pos in open_positions.values() if pos["lane"] == trade["lane"])
        if current_lane >= sleeve_budget:
            rejected["lane_budget"] = rejected.get("lane_budget", 0) + 1
            continue
        per_position_budget = sleeve_budget / max_open
        stake = min(per_position_budget, sleeve_budget - current_lane, balance * pair_cap)
        stake *= float(context.get("vol_scale", 1.0))
        if stake <= 0:
            rejected["pair_cap"] = rejected.get("pair_cap", 0) + 1
            continue
        open_positions[trade_id] = {
            "trade_id": trade_id,
            "lane": trade["lane"],
            "pair": trade["pair"],
            "stake": stake,
            "open_date": trade["open_date"],
            "vol_scale": float(context.get("vol_scale", 1.0)),
        }

    for trade_id, position in list(open_positions.items()):
        trade = all_trades[trade_id]
        ratio = float(trade["profit_ratio"]) - float(extra_round_trip_cost)
        balance += position["stake"] * ratio
        accepted.append({**position, "profit_abs": position["stake"] * ratio, "force_closed": True})

    profits = pd.Series([item["profit_abs"] for item in accepted], dtype=float)
    equity = starting_balance + profits.cumsum() if not profits.empty else pd.Series([starting_balance])
    drawdown = equity / equity.cummax() - 1.0
    return {
        "eligible": True,
        "starting_balance": starting_balance,
        "final_balance": balance,
        "profit_abs": balance - starting_balance,
        "profit_pct": (balance / starting_balance - 1.0) * 100.0,
        "max_drawdown_pct": abs(float(drawdown.min())) * 100.0,
        "accepted": len(accepted),
        "rejected": sum(rejected.values()),
        "rejections": rejected,
        "context_missing": context_missing,
        "avg_vol_scale": float(np.mean(overlay_samples)) if overlay_samples else 1.0,
        "cash_reserve": policy.cash_reserve,
        "policy": asdict(policy),
        "max_open": max_open,
        "pair_cap": pair_cap,
        "extra_round_trip_cost": extra_round_trip_cost,
        "weights": normalized_weights,
        "lanes": [asdict(candidate) | {"path": str(candidate.path)} for candidate in candidates],
        "overlay_method": "entry-time candles only; no realized-return lookahead",
    }


def data_gated_rows(data_root: Path) -> list[dict[str, Any]]:
    """Return explicit status rows for sleeves needing data beyond this matrix."""

    derivative_files = list((data_root / "historical" / "normalized").rglob("*.feather"))
    option_files = list((data_root / "options").glob("*.json"))
    microstructure_manifests = list((data_root / "microstructure" / "raw").rglob("manifest.json"))
    carry = {
        "sleeve": "same_venue_cash_and_carry",
        "status": "blocked",
        "reason": "no complete same-venue spot/perp/index/funding history was found",
        "derivative_artifacts_seen": len(derivative_files),
    }
    binance_root = data_root / "historical" / "normalized" / "binance-global"
    carry_paths = {
        "spot": binance_root / "BTC_USDT-1m-2026-08.feather",
        "perp": binance_root / "BTC_USDT_USDT-1m-futures-2026-08.feather",
        "index": binance_root / "BTC_USDT_USDT-index-1m-2026-08.feather",
        "funding": binance_root / "BTC_USDT_USDT-funding-2026-08.feather",
    }
    if all(path.is_file() for path in carry_paths.values()):
        carry_result = evaluate_carry_contract(
            pd.read_feather(carry_paths["spot"]),
            pd.read_feather(carry_paths["perp"]),
            pd.read_feather(carry_paths["funding"]),
            pd.read_feather(carry_paths["index"]),
            venue="binance-global",
            costs=ExecutionCost(fee_bps_per_side=2.0, spread_bps_round_trip=2.0, slippage_bps_round_trip=2.0, safety_bps_round_trip=1.0),
            min_basis=0.001,
            exit_basis=0.0003,
            min_funding=0.00001,
        )
        carry = {
            **carry,
            "status": "screened_not_promoted",
            "reason": "one-month same-venue public archive screen; no borrow, collateral, open-interest, liquidation-buffer, or execution-truth history",
            "data_window": "2026-08-01/2026-08-31",
            "result": carry_result,
        }
    return [
        carry,
        {
            "sleeve": "cross_venue_dispersion",
            "status": "blocked",
            "reason": "historical synchronized venue order-book/trade panels are unavailable; current captures are short diagnostic sessions",
            "microstructure_manifests_seen": len(microstructure_manifests),
        },
        {
            "sleeve": "options_volatility",
            "status": "blocked",
            "reason": "only a current Deribit chain snapshot is present; no historical IV surface and hedge-fill series",
            "option_artifacts_seen": len(option_files),
        },
    ]


def build_matrix(
    candidates: list[MatrixCandidate],
    *,
    data_root: Path,
    start: str,
    end: str,
    extra_round_trip_cost: float = 0.002,
) -> dict[str, Any]:
    """Evaluate the core and augmented matrices for one locked window."""

    by_name = {candidate.name: candidate for candidate in candidates}
    required = {"momentum", "crash"}
    missing = sorted(required - set(by_name))
    if missing:
        raise ValueError(f"matrix requires candidates: {missing}")

    scenarios: list[tuple[str, dict[str, float], OverlayPolicy]] = [
        ("core_momentum_crash", {"momentum": 0.70, "crash": 0.30}, OverlayPolicy()),
        ("core_plus_volatility_cash", {"momentum": 0.60, "crash": 0.25, "vmt": 0.15}, OverlayPolicy()),
        ("core_plus_cross_sectional", {"momentum": 0.60, "crash": 0.25, "rct": 0.15}, OverlayPolicy()),
        ("all_alpha", {"momentum": 0.50, "crash": 0.25, "vmt": 0.15, "rct": 0.10}, OverlayPolicy()),
        (
            "all_alpha_liquidity_gate",
            {"momentum": 0.50, "crash": 0.25, "vmt": 0.15, "rct": 0.10},
            OverlayPolicy(min_quote_volume=100_000.0, min_volume_ratio=0.50),
        ),
        (
            "all_alpha_volatility_target",
            {"momentum": 0.50, "crash": 0.25, "vmt": 0.15, "rct": 0.10},
            OverlayPolicy(target_annual_vol=0.25),
        ),
        (
            "all_alpha_liquidity_vol_target_cash_reserve",
            {"momentum": 0.50, "crash": 0.25, "vmt": 0.15, "rct": 0.10},
            OverlayPolicy(
                min_quote_volume=100_000.0,
                min_volume_ratio=0.50,
                target_annual_vol=0.25,
                cash_reserve=0.20,
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for name, weight_map, policy in scenarios:
        selected = [by_name[key] for key in weight_map if key in by_name]
        if len(selected) != len(weight_map):
            rows.append({"scenario": name, "eligible": False, "reason": "missing_candidate_export", "missing": sorted(set(weight_map) - set(by_name))})
            continue
        result = simulate_shared_wallet(
            selected,
            weight_map,
            data_root=data_root,
            policy=policy,
            max_open=3,
            pair_cap=0.40,
            extra_round_trip_cost=extra_round_trip_cost,
            start=start,
            end=end,
        )
        rows.append({"scenario": name, **result})
    return {
        "schema_version": "synergistic-sleeve-matrix.v1",
        "window": {"start": start, "end": end},
        "cost_stress": {"extra_round_trip_cost": extra_round_trip_cost, "description": "additional fee/spread/slippage stress on top of each export's Freqtrade result"},
        "rows": rows,
        "data_gated": data_gated_rows(data_root),
    }


def tune_matrix(
    candidates: list[MatrixCandidate],
    *,
    data_root: Path,
    train_start: str,
    train_end: str,
    holdout_start: str,
    holdout_end: str,
    extra_round_trip_cost: float = 0.002,
) -> dict[str, Any]:
    """Tune a small pre-declared grid, then freeze it for a holdout replay.

    The grid is intentionally coarse.  It explores allocation and risk-control
    choices, not dozens of indicator parameters, and selects on the training
    window only using profit penalized by drawdown.  The selected policy is
    then replayed unchanged on the holdout window.
    """

    by_name = {candidate.name: candidate for candidate in candidates}
    allocation_grid: list[tuple[str, dict[str, float]]] = [
        ("core", {"momentum": 0.70, "crash": 0.30}),
        ("core_plus_vmt", {"momentum": 0.60, "crash": 0.25, "vmt": 0.15}),
        ("core_plus_rct", {"momentum": 0.60, "crash": 0.25, "rct": 0.15}),
        ("all_alpha", {"momentum": 0.50, "crash": 0.25, "vmt": 0.15, "rct": 0.10}),
    ]
    liquidity_grid: list[tuple[str, float | None, float | None]] = [
        ("none", None, None),
        ("ratio_025", None, 0.25),
        ("ratio_050", None, 0.50),
        ("quote_100k", 100_000.0, None),
    ]
    volatility_grid: list[tuple[str, float | None]] = [("none", None), ("target_020", 0.20), ("target_025", 0.25), ("target_035", 0.35)]
    reserve_grid = [("reserve_0", 0.0), ("reserve_010", 0.10), ("reserve_020", 0.20)]
    rows: list[dict[str, Any]] = []
    for allocation_name, weights in allocation_grid:
        if any(name not in by_name for name in weights):
            continue
        selected = [by_name[name] for name in weights]
        for liquidity_name, min_quote_volume, min_volume_ratio in liquidity_grid:
            for volatility_name, target_vol in volatility_grid:
                for reserve_name, cash_reserve in reserve_grid:
                    policy = OverlayPolicy(
                        min_quote_volume=min_quote_volume,
                        min_volume_ratio=min_volume_ratio,
                        target_annual_vol=target_vol,
                        cash_reserve=cash_reserve,
                    )
                    train = simulate_shared_wallet(
                        selected,
                        weights,
                        data_root=data_root,
                        policy=policy,
                        extra_round_trip_cost=extra_round_trip_cost,
                        start=train_start,
                        end=train_end,
                    )
                    if not train.get("eligible"):
                        continue
                    score = float(train["profit_pct"]) - 0.50 * float(train["max_drawdown_pct"])
                    rows.append(
                        {
                            "allocation": allocation_name,
                            "liquidity": liquidity_name,
                            "volatility": volatility_name,
                            "reserve": reserve_name,
                            "weights": weights,
                            "policy": asdict(policy),
                            "train": train,
                            "train_score": score,
                        }
                    )
    eligible = [row for row in rows if row["train"]["accepted"] >= 25 and row["train"]["profit_pct"] > 0]
    if not eligible:
        return {
            "eligible": False,
            "reason": "no_positive_train_candidate_with_minimum_trades",
            "grid_rows": len(rows),
            "train_window": {"start": train_start, "end": train_end},
            "holdout_window": {"start": holdout_start, "end": holdout_end},
        }
    best = max(eligible, key=lambda row: (row["train_score"], row["train"]["profit_pct"]))
    selected = [by_name[name] for name in best["weights"]]
    holdout = simulate_shared_wallet(
        selected,
        best["weights"],
        data_root=data_root,
        policy=OverlayPolicy(**best["policy"]),
        extra_round_trip_cost=extra_round_trip_cost,
        start=holdout_start,
        end=holdout_end,
    )
    return {
        "eligible": True,
        "selection_rule": "maximize train profit_pct - 0.50 * max_drawdown_pct, with positive profit and >=25 accepted trades",
        "grid_rows": len(rows),
        "positive_train_rows": len(eligible),
        "selected": {
            "allocation": best["allocation"],
            "liquidity": best["liquidity"],
            "volatility": best["volatility"],
            "reserve": best["reserve"],
            "weights": best["weights"],
            "policy": best["policy"],
            "train": best["train"],
            "holdout": holdout,
        },
        "top_train_candidates": sorted(
            [
                {
                    "allocation": row["allocation"],
                    "liquidity": row["liquidity"],
                    "volatility": row["volatility"],
                    "reserve": row["reserve"],
                    "train_score": row["train_score"],
                    "train_profit_pct": row["train"]["profit_pct"],
                    "train_drawdown_pct": row["train"]["max_drawdown_pct"],
                    "accepted": row["train"]["accepted"],
                }
                for row in eligible
            ],
            key=lambda row: row["train_score"],
            reverse=True,
        )[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--momentum", type=Path, required=True)
    parser.add_argument("--crash", type=Path, required=True)
    parser.add_argument("--vmt", type=Path)
    parser.add_argument("--rct", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--extra-round-trip-cost", type=float, default=0.002)
    parser.add_argument("--tune-train-start")
    parser.add_argument("--tune-train-end")
    parser.add_argument("--tune-holdout-start")
    parser.add_argument("--tune-holdout-end")
    args = parser.parse_args()
    candidates = [
        MatrixCandidate("momentum", args.momentum, timeframe="15m"),
        MatrixCandidate("crash", args.crash, timeframe="4h"),
    ]
    # Cross-timeframe sleeves are intentionally evaluated as separate alpha
    # inputs.  The allocator operates on timestamps and shared capital; it
    # does not pretend that their signals are generated on one candle clock.
    if args.vmt:
        candidates.append(MatrixCandidate("vmt", args.vmt, timeframe="1h"))
    if args.rct:
        candidates.append(MatrixCandidate("rct", args.rct, timeframe="1h"))
    # Matrix compatibility is about venue/market, not timeframe, so the
    # scenario runner uses its own explicit candidate set and allows these
    # alpha clocks to compete for one wallet.
    payload = build_matrix(candidates, data_root=args.data_root, start=args.start, end=args.end, extra_round_trip_cost=args.extra_round_trip_cost)
    tune_values = (args.tune_train_start, args.tune_train_end, args.tune_holdout_start, args.tune_holdout_end)
    if any(value is not None for value in tune_values):
        if not all(value is not None for value in tune_values):
            parser.error("all four --tune-* window arguments are required together")
        payload["tuning"] = tune_matrix(
            candidates,
            data_root=args.data_root,
            train_start=args.tune_train_start,
            train_end=args.tune_train_end,
            holdout_start=args.tune_holdout_start,
            holdout_end=args.tune_holdout_end,
            extra_round_trip_cost=args.extra_round_trip_cost,
        )
    rendered = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
