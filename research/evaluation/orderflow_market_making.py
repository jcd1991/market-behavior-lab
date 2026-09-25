"""Order-flow and passive-quote research scaffold.

This lane intentionally refuses OHLCV-only inputs.  A market-making result
without venue-timestamped trades and L2 snapshots is not an execution result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

try:
    from .microstructure import normalize_minute_trades, normalize_orderbook_snapshots
except ImportError:  # Script execution from research/evaluation.
    from microstructure import normalize_minute_trades, normalize_orderbook_snapshots


@dataclass(frozen=True)
class QuotePolicy:
    half_spread_bps: float = 8.0
    inventory_limit: float = 1.0
    max_quote_notional: float = 100.0
    maker_fee_bps: float = 0.0
    adverse_selection_bps: float = 2.0


def validate_event_data(trades: pd.DataFrame | None, orderbooks: pd.DataFrame | None) -> dict[str, Any]:
    """Return a readiness report; never infer events from candles."""
    missing: list[str] = []
    if trades is None or trades.empty:
        missing.append("minute_trades")
    if orderbooks is None or orderbooks.empty:
        missing.append("orderbook_snapshots")
    trade_columns = set(trades.columns) if trades is not None else set()
    book_columns = set(orderbooks.columns) if orderbooks is not None else set()
    for column in ("timestamp", "price", "amount", "venue", "pair"):
        if column not in trade_columns:
            missing.append(f"trades.{column}")
    for column in ("timestamp", "bids", "asks", "venue", "pair"):
        if column not in book_columns:
            missing.append(f"orderbooks.{column}")
    return {"ready": not missing, "missing": sorted(set(missing)), "source": "venue-event-data"}


def simulate_passive_quotes(
    trades: pd.DataFrame,
    orderbooks: pd.DataFrame,
    *,
    policy: QuotePolicy = QuotePolicy(),
    initial_inventory: float = 0.0,
) -> dict[str, Any]:
    """Minimal event replay for queue/adverse-selection sensitivity.

    It is a screening model: a trade crossing our bid or ask is treated as a
    fill only when the displayed quote is touched.  It does not claim queue
    priority, so results must remain labeled hypothetical until exchange feed
    sequencing and queue modeling are added.
    """
    report = validate_event_data(trades, orderbooks)
    if not report["ready"]:
        return {"eligible": False, "reason": "missing_event_data", "validation": report}
    normalized_trades = normalize_minute_trades(trades, venue=str(trades.iloc[0]["venue"]), pair=str(trades.iloc[0]["pair"]), source="event-replay", market_type=str(trades.iloc[0].get("market_type", "spot")))
    normalized_books = normalize_orderbook_snapshots(orderbooks, venue=str(orderbooks.iloc[0]["venue"]), pair=str(orderbooks.iloc[0]["pair"]), source="event-replay", market_type=str(orderbooks.iloc[0].get("market_type", "spot")))
    books = normalized_books.set_index("timestamp")
    inventory = float(initial_inventory)
    cash = 0.0
    fills = 0
    for trade in normalized_trades.itertuples():
        available = books.index[books.index <= trade.timestamp]
        if len(available) == 0:
            continue
        book = books.loc[available[-1]]
        midpoint = float(book["midpoint"])
        if not midpoint:
            continue
        bid = midpoint * (1.0 - policy.half_spread_bps / 10000.0)
        ask = midpoint * (1.0 + policy.half_spread_bps / 10000.0)
        quantity = min(float(trade.amount), policy.max_quote_notional / midpoint)
        if trade.price <= bid and inventory + quantity <= policy.inventory_limit:
            inventory += quantity
            cash -= quantity * bid * (1.0 + policy.maker_fee_bps / 10000.0)
            fills += 1
        elif trade.price >= ask and inventory - quantity >= -policy.inventory_limit:
            inventory -= quantity
            cash += quantity * ask * (1.0 - policy.maker_fee_bps / 10000.0)
            fills += 1
    last_mid = float(normalized_books.iloc[-1]["midpoint"])
    mark_to_market = cash + inventory * last_mid
    return {"eligible": True, "fills": fills, "inventory": inventory, "cash": cash, "mark_to_market": mark_to_market, "policy": policy.__dict__, "warning": "Hypothetical passive fills; no queue priority or latency model."}
