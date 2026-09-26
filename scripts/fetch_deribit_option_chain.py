#!/usr/bin/env python3
"""Capture a bounded public Deribit option-chain snapshot.

This is a discovery/market-structure capture, not historical execution data.
The output is intentionally source-labelled so it cannot be mistaken for a
backtestable option history or for a Freqtrade execution feed.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://www.deribit.com/api/v2/public/"


def _get(method: str, params: dict[str, object]) -> dict:
    url = f"{BASE_URL}{method}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "market-behavior-lab/0.1"})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _iso_ms(value: object) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).isoformat()


def normalize_ticker(instrument: dict, ticker: dict, captured_at: str) -> dict:
    return {
        "timestamp": captured_at,
        "instrument": instrument.get("instrument_name"),
        "currency": instrument.get("base_currency"),
        "option_type": instrument.get("option_type"),
        "strike": instrument.get("strike"),
        "expiry": _iso_ms(instrument.get("expiration_timestamp")),
        "bid": ticker.get("best_bid_price"),
        "ask": ticker.get("best_ask_price"),
        "mark": ticker.get("mark_price"),
        "mark_iv": ticker.get("mark_iv"),
        "delta": ticker.get("greeks", {}).get("delta"),
        "underlying_price": ticker.get("underlying_price"),
        "volume_24h": ticker.get("stats", {}).get("volume"),
        "open_interest": ticker.get("open_interest"),
    }


def capture(currency: str, limit: int) -> dict:
    captured_at = datetime.now(timezone.utc).isoformat()
    result = _get("get_instruments", {"currency": currency, "kind": "option", "expired": "false"})
    instruments = result.get("result", [])
    instruments = sorted(
        instruments,
        key=lambda item: (item.get("expiration_timestamp") or 0, item.get("strike") or 0),
    )[:limit]
    rows = []
    failures = []
    for instrument in instruments:
        name = instrument.get("instrument_name")
        try:
            ticker = _get("ticker", {"instrument_name": name}).get("result", {})
            rows.append(normalize_ticker(instrument, ticker, captured_at))
        except Exception as exc:  # bounded discovery capture: keep successful rows
            failures.append({"instrument": name, "error": str(exc)})
    return {
        "schema_version": "option-chain.v1",
        "captured_at": captured_at,
        "source": "deribit-public-api",
        "execution_truth": False,
        "historical": False,
        "currency": currency,
        "rows": rows,
        "failures": failures,
        "provenance": "public option-chain snapshot; indicative and not a historical fill series",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--currency", choices=("BTC", "ETH"), default="BTC")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = capture(args.currency, max(1, min(args.limit, 100)))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": payload["source"], "currency": args.currency, "rows": len(payload["rows"]), "failures": len(payload["failures"]), "historical": payload["historical"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
