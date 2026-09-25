#!/usr/bin/env python3
"""Capture bounded public crypto market-data sessions.

This is a research-ingestion helper, not an exchange adapter or trading bot.
It uses unauthenticated public WebSocket feeds and writes raw JSONL plus a
manifest under an ignored local data directory. It never accepts API keys.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable
from uuid import uuid4


SCHEMA_VERSION = "microstructure.raw.v1"
DEFAULT_OUTPUT_ROOT = Path("user_data/data/microstructure/raw")


@dataclass(frozen=True)
class CaptureConfig:
    venue: str
    pairs: tuple[str, ...]
    market_type: str
    seconds: float
    output_root: Path
    depth: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "unknown"


def canonical_pair(value: str) -> str:
    """Canonicalize common spot/perpetual input forms."""

    raw = value.strip().upper().replace("-", "/")
    if ":" in raw:
        base_quote, settlement = raw.split(":", 1)
        if "/" not in base_quote:
            raise ValueError(f"pair must contain base/quote: {value}")
        return f"{base_quote}:{settlement}"
    if "/" not in raw:
        raise ValueError(f"pair must contain base/quote: {value}")
    return raw


def split_pair(pair: str) -> tuple[str, str, str | None]:
    canonical = canonical_pair(pair)
    base_quote, _, settlement = canonical.partition(":")
    base, quote = base_quote.split("/", 1)
    return base, quote, settlement or None


def coinbase_product(pair: str) -> str:
    base, quote, settlement = split_pair(pair)
    if settlement:
        raise ValueError("Coinbase capture currently supports spot pairs only")
    return f"{base}-{quote}"


def okx_instrument(pair: str, market_type: str) -> str:
    base, quote, settlement = split_pair(pair)
    if market_type == "futures":
        return f"{base}-{quote}-SWAP"
    if settlement:
        raise ValueError("spot OKX pairs must not include a settlement suffix")
    return f"{base}-{quote}"


def binance_symbol(pair: str) -> str:
    base, quote, _ = split_pair(pair)
    return f"{base}{quote}".lower()


def kraken_symbol(pair: str) -> str:
    base, quote, settlement = split_pair(pair)
    if settlement:
        raise ValueError("Kraken capture currently supports spot pairs only")
    return f"{base}/{quote}"


def build_subscriptions(config: CaptureConfig) -> tuple[str, list[dict[str, Any]]]:
    """Return the public endpoint and JSON subscription messages."""

    if not config.pairs:
        raise ValueError("at least one pair is required")

    if config.venue == "coinbase":
        products = [coinbase_product(pair) for pair in config.pairs]
        return (
            "wss://advanced-trade-ws.coinbase.com",
            [
                {"type": "subscribe", "product_ids": products, "channel": "level2"},
                {"type": "subscribe", "product_ids": products, "channel": "market_trades"},
            ],
        )

    if config.venue == "okx":
        instruments = [okx_instrument(pair, config.market_type) for pair in config.pairs]
        channels = ["books", "trades"]
        if config.market_type == "futures":
            channels.extend(["mark-price", "funding-rate", "open-interest"])
        args = [
            {"channel": channel, "instId": instrument}
            for channel in channels
            for instrument in instruments
        ]
        return "wss://ws.okx.com:8443/ws/v5/public", [{"op": "subscribe", "args": args}]

    if config.venue == "binance":
        if config.market_type == "futures":
            stream_names = (
                [f"{binance_symbol(pair)}@aggTrade" for pair in config.pairs]
                + [f"{binance_symbol(pair)}@depth@100ms" for pair in config.pairs]
                + [f"{binance_symbol(pair)}@markPrice@1s" for pair in config.pairs]
            )
            endpoint = "wss://fstream.binance.com/stream?streams="
        else:
            stream_names = (
                [f"{binance_symbol(pair)}@trade" for pair in config.pairs]
                + [f"{binance_symbol(pair)}@depth@100ms" for pair in config.pairs]
            )
            endpoint = "wss://stream.binance.com:9443/stream?streams="
        return endpoint + "/".join(stream_names), []

    if config.venue == "kraken":
        symbols = [kraken_symbol(pair) for pair in config.pairs]
        return "wss://ws.kraken.com/v2", [
            {
                "method": "subscribe",
                "params": {"channel": "book", "symbol": symbols, "depth": config.depth, "snapshot": True},
            },
            {
                "method": "subscribe",
                "params": {"channel": "trade", "symbol": symbols, "snapshot": False},
            },
        ]

    raise ValueError(f"unsupported venue: {config.venue}")


class CaptureWriter:
    """Write raw events and a machine-readable capture manifest."""

    def __init__(self, config: CaptureConfig, endpoint: str) -> None:
        started = utc_now()
        session = started.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        self.started = started
        self.config = config
        self.endpoint = endpoint
        self.session_id = session
        self.directory = config.output_root / safe_component(config.venue) / safe_component(config.market_type) / session
        self.directory.mkdir(parents=True, exist_ok=True)
        self.events_path = self.directory / "events.jsonl"
        self.manifest_path = self.directory / "manifest.json"
        self._events = self.events_path.open("w", encoding="utf-8")
        self.message_count = 0
        self.byte_count = 0
        self.errors: list[str] = []

    def write_control(self, payload: dict[str, Any]) -> None:
        self.write_payload(payload, event_type="control")

    def write_payload(self, payload: Any, *, event_type: str = "market_data") -> None:
        record = {
            "schema_version": SCHEMA_VERSION,
            "received_at": iso_utc(utc_now()),
            "venue": self.config.venue,
            "market_type": self.config.market_type,
            "pairs": list(self.config.pairs),
            "event_type": event_type,
            "payload": payload,
        }
        encoded = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
        self._events.write(encoded + "\n")
        self._events.flush()
        self.message_count += 1
        self.byte_count += len(encoded.encode("utf-8")) + 1

    def add_error(self, message: str) -> None:
        self.errors.append(message[:500])

    def close(self, *, status: str) -> Path:
        self._events.close()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "venue": self.config.venue,
            "market_type": self.config.market_type,
            "pairs": list(self.config.pairs),
            "endpoint": self.endpoint,
            "source": f"{self.config.venue}-public-websocket",
            "started_at": iso_utc(self.started),
            "ended_at": iso_utc(utc_now()),
            "requested_seconds": self.config.seconds,
            "message_count": self.message_count,
            "byte_count": self.byte_count,
            "status": status,
            "errors": self.errors,
            "files": {"events": self.events_path.name},
            "execution_truth": False,
            "notes": [
                "Raw public market data; normalize and audit before research use.",
                "Not a substitute for venue-matched Freqtrade execution candles.",
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return self.manifest_path


def decode_message(message: str | bytes) -> Any:
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    try:
        return json.loads(message)
    except json.JSONDecodeError:
        return {"raw_text": message}


async def capture(config: CaptureConfig) -> Path:
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - exercised by CLI users
        raise RuntimeError(
            "websockets is required; install the optional capture dependencies "
            "with: python -m pip install -e '.[capture]'"
        ) from exc

    endpoint, subscriptions = build_subscriptions(config)
    writer = CaptureWriter(config, endpoint)
    deadline = asyncio.get_running_loop().time() + config.seconds
    try:
        async with websockets.connect(endpoint, ping_interval=20, ping_timeout=20, close_timeout=5, max_size=None) as socket:
            for subscription in subscriptions:
                await socket.send(json.dumps(subscription))
                writer.write_control(subscription)
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    message = await asyncio.wait_for(socket.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                writer.write_payload(decode_message(message))
        status = "complete"
    except Exception as exc:
        writer.add_error(f"{type(exc).__name__}: {exc}")
        status = "error"
    return writer.close(status=status)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venue", choices=("coinbase", "okx", "binance", "kraken"), required=True)
    parser.add_argument("--pair", action="append", required=True, dest="pairs")
    parser.add_argument("--market-type", choices=("spot", "futures"), default="spot")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def parse_config(argv: Iterable[str] | None = None) -> CaptureConfig:
    args = build_parser().parse_args(argv)
    if args.seconds <= 0 or args.seconds > 3600:
        raise ValueError("--seconds must be greater than 0 and no more than 3600")
    pairs = tuple(dict.fromkeys(canonical_pair(pair) for pair in args.pairs))
    if args.venue == "coinbase" and args.market_type != "spot":
        raise ValueError("Coinbase capture is spot-only in this collector")
    if args.venue == "kraken" and args.market_type != "spot":
        raise ValueError("Kraken capture is spot-only in this collector")
    return CaptureConfig(args.venue, pairs, args.market_type, args.seconds, args.output_root, args.depth)


def main(argv: Iterable[str] | None = None) -> int:
    try:
        config = parse_config(argv)
        manifest = asyncio.run(capture(config))
    except (ValueError, RuntimeError) as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 2
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
