from __future__ import annotations

from pathlib import Path
import zipfile

import pandas as pd

from scripts.normalize_free_historical import normalize_archives, write_normalized


def _zip_csv(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("candles.csv", text)


def test_normalizes_binance_microsecond_archive(tmp_path: Path) -> None:
    archive = tmp_path / "BTCUSDT-1m.zip"
    _zip_csv(
        archive,
        "1704067200000000,100,101,99,100.5,2,1704067259999000,201,4,1,100.5,0\n"
        "1704067260000000,100.5,102,100,101.5,3,1704067319999000,304,5,2,203,0\n",
    )
    frame = normalize_archives([archive], provider="binance")
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert frame["date"].dt.tz is not None
    assert frame.iloc[0]["date"] == pd.Timestamp("2024-01-01T00:00:00Z")
    assert frame.iloc[1]["volume"] == 3


def test_normalizes_okx_millisecond_archive_with_header(tmp_path: Path) -> None:
    archive = tmp_path / "BTC-USDT-SWAP-candles.zip"
    _zip_csv(
        archive,
        "instrument_name,open,high,low,close,vol,vol_ccy,vol_quote,open_time,confirm\n"
        "BTC-USDT-SWAP,100,101,99,100.5,2,200,201,1704067200000,1\n",
    )
    frame = normalize_archives([archive], provider="okx")
    assert len(frame) == 1
    assert frame.iloc[0]["date"] == pd.Timestamp("2024-01-01T00:00:00Z")


def test_write_normalized_records_provenance_and_pair_contract(tmp_path: Path) -> None:
    archive = tmp_path / "BTCUSDT-1m.zip"
    _zip_csv(archive, "1704067200000000,100,101,99,100.5,2,0,0,1,1,1,0\n")
    output = tmp_path / "normalized" / "BTC_USDT-1m.feather"
    manifest = write_normalized(
        [archive],
        output,
        provider="binance",
        pair="BTC/USDT",
        market_type="spot",
        source="binance-global-public-archive",
    )
    assert output.exists()
    assert output.with_suffix(".feather.manifest.json").exists()
    assert manifest["execution_truth"] is False
    assert manifest["timestamps"] == "UTC"
