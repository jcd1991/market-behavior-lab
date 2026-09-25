"""Shared-wallet and expected-fill reconciliation primitives.

The simulator is intentionally small and deterministic.  It is not an order
router.  Its purpose is to stop independent Freqtrade exports from being
presented as a portfolio result when they would compete for the same wallet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

try:
    from .microstructure import VenueCostModel, depth_cost_bps
except ImportError:  # Script execution from research/evaluation.
    from microstructure import VenueCostModel, depth_cost_bps


@dataclass(frozen=True)
class WalletPolicy:
    starting_balance: float = 1000.0
    max_open_positions: int = 3
    max_pair_fraction: float = 0.25
    max_gross_fraction: float = 1.0
    default_notional_fraction: float = 0.25


def _as_utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def simulate_shared_wallet(
    trades: pd.DataFrame,
    *,
    policy: WalletPolicy = WalletPolicy(),
    costs: VenueCostModel | None = None,
    tier: str | None = None,
    orderbooks: dict[tuple[str, pd.Timestamp], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replay candidate trades with one balance, overlap, and concentration.

    Required columns are ``open_time``, ``close_time``, ``pair``, ``side`` and
    ``profit_ratio``.  A precomputed ``stake_fraction`` can override the
    default stake.  Order-book snapshots are optional; when present, the
    nearest exact timestamp is used and a missing book rejects the trade
    rather than silently assuming zero slippage.
    """
    required = {"open_time", "close_time", "pair", "side", "profit_ratio"}
    if not required.issubset(trades.columns):
        raise ValueError(f"trades missing required columns: {sorted(required - set(trades.columns))}")
    if policy.starting_balance <= 0 or policy.max_open_positions < 1 or not 0 < policy.max_pair_fraction <= 1:
        raise ValueError("wallet policy has invalid limits")
    frame = trades.copy()
    frame["open_time"] = frame["open_time"].map(_as_utc)
    frame["close_time"] = frame["close_time"].map(_as_utc)
    frame = frame[frame["close_time"] > frame["open_time"]].sort_values(["open_time", "close_time", "pair"]).reset_index(drop=True)
    active: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    balance = float(policy.starting_balance)

    def reject(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    for index, row in frame.iterrows():
        now = row["open_time"]
        still_open: list[dict[str, Any]] = []
        for position in active:
            if position["close_time"] > now:
                still_open.append(position)
            else:
                balance += position["stake"] * position["net_ratio"]
                accepted.append(position)
        active = still_open
        pair = str(row["pair"])
        if any(position["pair"] == pair for position in active):
            reject("pair_overlap")
            continue
        if len(active) >= policy.max_open_positions:
            reject("max_open_positions")
            continue
        stake_fraction = float(row.get("stake_fraction", policy.default_notional_fraction) or policy.default_notional_fraction)
        stake = min(balance * stake_fraction, balance * policy.max_pair_fraction)
        gross_open = sum(float(position["stake"]) for position in active)
        if gross_open + stake > balance * policy.max_gross_fraction:
            stake = max(0.0, balance * policy.max_gross_fraction - gross_open)
        if stake <= 0:
            reject("wallet_capacity")
            continue
        ratio = float(row["profit_ratio"])
        fee_ratio = 0.0
        slippage_ratio = 0.0
        venue = str(row.get("venue", costs.venue if costs else "unknown"))
        if costs is not None:
            fee_ratio = 2.0 * costs.fee_bps(liquidity=str(row.get("liquidity", "taker")), tier=tier) / 10000.0
            slippage_ratio = 2.0 * costs.safety_bps / 10000.0
            if orderbooks is not None:
                key = (pair, now)
                book = orderbooks.get(key)
                if book is None:
                    reject("missing_orderbook")
                    continue
                side = "buy" if str(row["side"]).lower() in {"long", "buy"} else "sell"
                entry_cost = depth_cost_bps(book, side=side, notional=stake)
                if not entry_cost.get("filled"):
                    reject("insufficient_orderbook_depth")
                    continue
                slippage_ratio += float(entry_cost.get("slippage_bps") or 0.0) / 10000.0 * 2.0
        active.append({
            "trade_index": int(index), "pair": pair, "side": str(row["side"]),
            "venue": venue, "open_time": now, "close_time": row["close_time"],
            "stake": stake, "gross_ratio": ratio, "fee_ratio": fee_ratio,
            "slippage_ratio": slippage_ratio, "net_ratio": ratio - fee_ratio - slippage_ratio,
        })

    for position in active:
        balance += position["stake"] * position["net_ratio"]
        accepted.append({**position, "force_closed": True})
    accepted_frame = pd.DataFrame(accepted)
    return {
        "starting_balance": policy.starting_balance,
        "final_balance": balance,
        "profit_abs": balance - policy.starting_balance,
        "profit_pct": (balance / policy.starting_balance - 1.0) * 100.0,
        "accepted": len(accepted),
        "rejected": sum(rejected.values()),
        "rejections": rejected,
        "max_open_positions": policy.max_open_positions,
        "max_pair_fraction": policy.max_pair_fraction,
        "trades": accepted_frame.to_dict(orient="records") if not accepted_frame.empty else [],
    }


def reconcile_fills(
    expected: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    price_tolerance_bps: float = 25.0,
    amount_tolerance: float = 1e-9,
) -> dict[str, Any]:
    """Compare expected dry-run fills with observed fills by order id."""
    required = {"order_id", "price", "amount", "timestamp"}
    if not required.issubset(expected.columns) or not required.issubset(actual.columns):
        raise ValueError("expected and actual fills require order_id, price, amount, timestamp")
    left = expected.copy().set_index("order_id")
    right = actual.copy().set_index("order_id")
    rows: list[dict[str, Any]] = []
    for order_id in sorted(set(left.index) | set(right.index)):
        exp = left.loc[order_id] if order_id in left.index else None
        act = right.loc[order_id] if order_id in right.index else None
        if exp is None:
            rows.append({"order_id": order_id, "status": "unexpected_actual"})
            continue
        if act is None:
            rows.append({"order_id": order_id, "status": "missing_actual"})
            continue
        expected_price = float(exp["price"])
        actual_price = float(act["price"])
        price_error_bps = (actual_price / expected_price - 1.0) * 10000.0 if expected_price else float("inf")
        amount_error = float(act["amount"]) - float(exp["amount"])
        status = "within_tolerance" if abs(price_error_bps) <= price_tolerance_bps and abs(amount_error) <= amount_tolerance else "outside_tolerance"
        rows.append({"order_id": order_id, "status": status, "price_error_bps": price_error_bps, "amount_error": amount_error})
    matched = [row for row in rows if row["status"] in {"within_tolerance", "outside_tolerance"}]
    return {
        "schema_version": "reconciliation.v1",
        "expected_count": len(expected),
        "actual_count": len(actual),
        "within_tolerance": sum(row["status"] == "within_tolerance" for row in rows),
        "outside_tolerance": sum(row["status"] == "outside_tolerance" for row in rows),
        "missing_actual": sum(row["status"] == "missing_actual" for row in rows),
        "unexpected_actual": sum(row["status"] == "unexpected_actual" for row in rows),
        "mean_price_error_bps": sum(float(row.get("price_error_bps", 0.0)) for row in matched) / len(matched) if matched else None,
        "fills": rows,
    }
