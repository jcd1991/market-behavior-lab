from pathlib import Path
import zipfile

import pandas as pd

from scripts.normalize_binance_derivatives import normalize
from scripts.normalize_binance_metrics_series import normalize_series


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


def test_normalizes_binance_metrics_archive(tmp_path: Path) -> None:
    archive = tmp_path / "metrics.zip"
    _zip(
        archive,
        "BTCUSDT-metrics-2026-08-01.csv",
        "create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio\n"
        "1754006400000,BTCUSDT,123.4,9876543.21,1.2\n",
    )
    frame, manifest = normalize(
        archive,
        kind="metrics",
        pair="BTC/USDT:USDT",
        source="binance-global-public-archive",
    )
    assert frame.iloc[0]["open_interest"] == 123.4
    assert frame.iloc[0]["open_interest_usd"] == 9876543.21
    assert frame.iloc[0]["count_toptrader_long_short_ratio"] == 1.2
    assert manifest["kind"] == "metrics"


def test_combines_binance_metrics_series(tmp_path: Path) -> None:
    for day, timestamp in (("01", "1754006400000"), ("02", "1754092800000")):
        _zip(
            tmp_path / f"um-BTCUSDT-metrics-2026-08-{day}.zip",
            f"BTCUSDT-metrics-2026-08-{day}.csv",
            "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
            f"{timestamp},BTCUSDT,123.4,9876543.21\n",
        )
    frame, manifest = normalize_series(
        sorted(tmp_path.glob("*.zip")),
        pair="BTC/USDT:USDT",
        source="binance-global-public-archive",
    )
    assert len(frame) == 2
    assert manifest["input_count"] == 2


def test_normalizes_binance_metrics_string_timestamp(tmp_path: Path) -> None:
    archive = tmp_path / "metrics-string.zip"
    _zip(
        archive,
        "BTCUSDT-metrics-2026-08-01.csv",
        "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
        "2026-08-01 03:10:00,BTCUSDT,123.4,9876543.21\n",
    )
    frame, _ = normalize(archive, kind="metrics", pair="BTC/USDT:USDT", source="test")
    assert str(frame.iloc[0]["date"]) == "2026-08-01 03:10:00+00:00"
    assert frame.iloc[0]["available_at"] is pd.NaT


def test_metrics_availability_handles_start_and_end_labeled_files(tmp_path: Path) -> None:
    old = tmp_path / "um-BTCUSDT-metrics-2026-06-24.zip"
    new = tmp_path / "um-BTCUSDT-metrics-2026-06-25.zip"
    header = "create_time,symbol,sum_open_interest,sum_open_interest_value\n"
    old_times = pd.date_range("2026-06-24 00:05:00", periods=288, freq="5min", tz="UTC")
    new_times = pd.date_range("2026-06-25 00:00:00", periods=288, freq="5min", tz="UTC")
    old_rows = "".join(f"{stamp.strftime('%Y-%m-%d %H:%M:%S')},BTCUSDT,1,2\n" for stamp in old_times)
    new_rows = "".join(f"{stamp.strftime('%Y-%m-%d %H:%M:%S')},BTCUSDT,3,4\n" for stamp in new_times)
    _zip(old, "BTCUSDT-metrics-2026-06-24.csv", header + old_rows)
    _zip(new, "BTCUSDT-metrics-2026-06-25.csv", header + new_rows)
    old_frame, old_manifest = normalize(old, kind="metrics", pair="BTC/USDT:USDT", source="test")
    new_frame, new_manifest = normalize(new, kind="metrics", pair="BTC/USDT:USDT", source="test")
    assert old_manifest["metrics_label_convention"] == "end_labeled"
    assert new_manifest["metrics_label_convention"] == "start_labeled"
    assert old_frame.iloc[0]["available_at"] == old_frame.iloc[0]["date"]
    assert new_frame.iloc[0]["available_at"] == new_frame.iloc[0]["date"] + pd.Timedelta(minutes=5)
