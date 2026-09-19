#!/usr/bin/env python3
"""Measure current public order-book spread and depth slippage.

These snapshots are execution-cost observations for calibration only. They are
not historical data and must never be merged into backtest candles or used to
claim that a historical trade paid the observed current cost.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

import ccxt


def _walk(levels: list[list[float]], notional: float) -> tuple[float | None, float | None]:
    remaining = float(notional)
    acquired = 0.0
    spent = 0.0
    for price, amount, *_ in levels:
        price = float(price)
        amount = float(amount)
        if price <= 0 or amount <= 0:
            continue
        value = min(remaining, price * amount)
        acquired += value / price
        spent += value
        remaining -= value
        if remaining <= 1e-12:
            break
    if remaining > 1e-9 or acquired <= 0:
        return None, None
    return spent / acquired, (spent / acquired)


def measure(book: dict[str, Any], notional: float) -> dict[str, float | None]:
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    if not bids or not asks:
        return {"spread_bps": None, "buy_slippage_bps": None, "sell_slippage_bps": None}
    bid = float(bids[0][0])
    ask = float(asks[0][0])
    midpoint = (bid + ask) / 2.0
    buy_vwap, _ = _walk(asks, notional)
    sell_vwap, _ = _walk([[price, amount] for price, amount, *_ in bids], notional)
    return {
        "spread_bps": (ask - bid) / midpoint * 10000.0,
        "buy_slippage_bps": None if buy_vwap is None else (buy_vwap - midpoint) / midpoint * 10000.0,
        "sell_slippage_bps": None if sell_vwap is None else (midpoint - sell_vwap) / midpoint * 10000.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", required=True, choices=("binanceus", "coinbase", "kraken"))
    parser.add_argument("--pair", action="append", required=True)
    parser.add_argument("--notional", type=float, default=20.0)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    exchange = getattr(ccxt, args.exchange)({"enableRateLimit": True})
    observed_at = datetime.now(timezone.utc).isoformat()
    output: list[dict[str, Any]] = []
    try:
        exchange.load_markets()
        for pair in args.pair:
            try:
                book = exchange.fetch_order_book(pair, limit=args.limit)
                row = {"exchange": args.exchange, "pair": pair, "notional": args.notional, "observed_at": observed_at}
                row.update(measure(book, args.notional))
                output.append(row)
            except Exception as exc:  # Public availability varies by venue/pair.
                output.append({"exchange": args.exchange, "pair": pair, "notional": args.notional, "observed_at": observed_at, "error": type(exc).__name__})
    finally:
        close = getattr(exchange, "close", None)
        if close is not None:
            close()
    print(json.dumps({"source": "public-orderbook-snapshot", "historical": False, "rows": output}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
