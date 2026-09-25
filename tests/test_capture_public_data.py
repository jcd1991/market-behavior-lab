import json
from pathlib import Path

import pytest

from scripts.capture_public_data import (
    CaptureConfig,
    CaptureWriter,
    binance_symbol,
    build_subscriptions,
    canonical_pair,
    coinbase_product,
    okx_instrument,
    parse_config,
)


def test_pair_normalization_preserves_perpetual_settlement() -> None:
    assert canonical_pair("btc-usdt:usdt") == "BTC/USDT:USDT"
    assert coinbase_product("btc/usd") == "BTC-USD"
    assert okx_instrument("BTC/USDT:USDT", "futures") == "BTC-USDT-SWAP"
    assert binance_symbol("BTC/USDT:USDT") == "btcusdt"


def test_coinbase_builds_public_channel_subscriptions() -> None:
    config = CaptureConfig("coinbase", ("BTC/USD", "ETH/USD"), "spot", 5, Path("."), 10)
    endpoint, messages = build_subscriptions(config)
    assert endpoint == "wss://advanced-trade-ws.coinbase.com"
    assert [message["channel"] for message in messages] == ["level2", "market_trades"]
    assert all(message["product_ids"] == ["BTC-USD", "ETH-USD"] for message in messages)


def test_okx_futures_includes_derivative_channels() -> None:
    config = CaptureConfig("okx", ("BTC/USDT:USDT",), "futures", 5, Path("."), 10)
    _, messages = build_subscriptions(config)
    channels = {arg["channel"] for arg in messages[0]["args"]}
    assert {"books", "trades", "mark-price", "funding-rate", "open-interest"} <= channels


def test_invalid_market_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="spot-only"):
        parse_config(["--venue", "coinbase", "--market-type", "futures", "--pair", "BTC/USD"])


def test_capture_writer_writes_raw_events_and_manifest(tmp_path: Path) -> None:
    config = CaptureConfig("coinbase", ("BTC/USD",), "spot", 1, tmp_path, 10)
    writer = CaptureWriter(config, "wss://example.invalid")
    writer.write_payload({"type": "test"})
    manifest_path = writer.close(status="complete")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    events_path = manifest_path.parent / manifest["files"]["events"]
    event = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])
    assert manifest["schema_version"] == "microstructure.raw.v1"
    assert manifest["execution_truth"] is False
    assert manifest["message_count"] == 1
    assert event["received_at"].endswith("Z")
    assert event["payload"] == {"type": "test"}
