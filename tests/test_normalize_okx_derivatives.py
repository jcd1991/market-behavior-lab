from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.normalize_okx_derivatives import normalize, write_normalized


def _response(path: Path, rows: list) -> None:
    path.write_text(json.dumps({"code": "0", "msg": "", "data": rows}), encoding="utf-8")


def test_normalizes_okx_funding_rows(tmp_path: Path) -> None:
    source = tmp_path / "funding.json"
    _response(source, [{"instId": "BTC-USDT-SWAP", "fundingTime": "1704067200000", "fundingRate": "0.001"}])
    frame = normalize(source, kind="funding")
    assert frame.iloc[0]["date"] == pd.Timestamp("2024-01-01T00:00:00Z")
    assert frame.iloc[0]["funding_rate"] == 0.001


def test_normalizes_okx_open_interest_and_records_manifest(tmp_path: Path) -> None:
    source = tmp_path / "oi.json"
    _response(source, [{"instId": "BTC-USDT-SWAP", "ts": "1704067200000", "oi": "10", "oiUsd": "400000"}])
    output = tmp_path / "oi.feather"
    manifest = write_normalized(source, output, kind="open-interest", pair="BTC/USDT:USDT", source="okx-public-api")
    assert output.exists()
    assert manifest["kind"] == "open-interest"
    assert manifest["execution_truth"] is False
