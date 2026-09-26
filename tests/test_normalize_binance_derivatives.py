from pathlib import Path
import zipfile

from scripts.normalize_binance_derivatives import normalize


def _zip(path: Path, name: str, text: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, text)


def test_normalizes_binance_index_kline_archive(tmp_path: Path) -> None:
    archive = tmp_path / "index.zip"
    _zip(
        archive,
        "BTCUSDT-1m.csv",
        "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
        "1704067200000,100,101,99,100.5,0,1704067259999,0,60,0,0,0\n",
    )
    frame, manifest = normalize(archive, kind="indexPriceKlines", pair="BTC/USDT:USDT", source="binance-global-public-archive")
    assert frame.iloc[0]["index_close"] == 100.5
    assert manifest["execution_truth"] is False


def test_normalizes_binance_funding_archive(tmp_path: Path) -> None:
    archive = tmp_path / "funding.zip"
    _zip(archive, "BTCUSDT.csv", "calc_time,funding_interval_hours,last_funding_rate\n1704067200000,8,0.0001\n")
    frame, manifest = normalize(archive, kind="fundingRate", pair="BTC/USDT:USDT", source="binance-global-public-archive")
    assert frame.iloc[0]["funding_rate"] == 0.0001
    assert frame.iloc[0]["funding_interval_hours"] == 8
    assert manifest["venue_mixing"] == "forbidden"
