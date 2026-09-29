import json
from pathlib import Path

from scripts.fetch_free_historical import (
    binance_plan,
    bitmex_plan,
    coinmetrics_plan,
    kraken_plan,
    tardis_plan,
)


def namespace(**kwargs):
    return type("Args", (), kwargs)()


def test_binance_monthly_url_and_filename() -> None:
    plan = binance_plan(
        namespace(
            symbol="BTCUSDT",
            market_type="spot",
            futures_market="um",
            dataset="klines",
            interval="1m",
            month="2026-08",
            date=None,
        )
    )
    assert plan.url.endswith("/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2026-08.zip")
    assert plan.output_name == "spot-BTCUSDT-1m-2026-08.zip"


def test_binance_spot_and_futures_local_names_are_distinct() -> None:
    common = dict(
        symbol="BTCUSDT",
        futures_market="um",
        dataset="klines",
        interval="1m",
        month="2026-08",
        date=None,
    )
    spot = binance_plan(namespace(market_type="spot", **common))
    futures = binance_plan(namespace(market_type="futures", **common))
    assert spot.output_name != futures.output_name
    assert futures.output_name.startswith("um-")
    assert futures.url.endswith("/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2026-08.zip")


def test_binance_daily_metrics_url() -> None:
    plan = binance_plan(
        namespace(
            symbol="BTCUSDT",
            market_type="futures",
            futures_market="um",
            dataset="metrics",
            interval=None,
            month=None,
            date="2026-08-01",
        )
    )
    assert plan.url.endswith("/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-08-01.zip")
    assert plan.output_name == "um-BTCUSDT-metrics-2026-08-01.zip"


def test_bitmex_public_archive_url() -> None:
    plan = bitmex_plan(namespace(dataset="quote", date="2015-01-01"))
    assert plan.url.endswith("/data/quote/20150101.csv.gz")


def test_kraken_quarter_is_archive_not_rest_page() -> None:
    plan = kraken_plan(namespace(quarter="2026Q2", pair=None, since=None))
    assert plan.source_kind == "venue-native-public-archive"
    assert plan.url.endswith("Kraken_Trades_2026Q2.zip")


def test_tardis_first_of_month_dataset_url() -> None:
    plan = tardis_plan(
        namespace(
            exchange="deribit",
            dataset="trades",
            date="2025-03-01",
            symbol="BTC-PERPETUAL",
            group=None,
        )
    )
    assert plan.url.endswith("/deribit/trades/2025/03/01/BTC-PERPETUAL.csv.gz")


def test_coinmetrics_catalog_url_is_credential_free() -> None:
    plan = coinmetrics_plan(
        namespace(
            dataset="catalog-market-orderbooks",
            limit=5,
            market=None,
            start=None,
            end=None,
            frequency=None,
            page_size=None,
        )
    )
    assert plan.url == "https://community-api.coinmetrics.io/v4/catalog-all/market-orderbooks?limit=5"


def test_okx_public_historical_query_url() -> None:
    from scripts.fetch_free_historical import okx_plan

    plan = okx_plan(
        namespace(
            dataset="market-data-history",
            inst_id=None,
            inst_type="SWAP",
            bar=None,
            limit=None,
            after=None,
            before=None,
            module=2,
            inst_id_list=None,
            inst_family_list="BTC-USDT",
            date_aggr_type="daily",
            begin="1788220800000",
            end="1788307200000",
        )
    )
    assert "public/market-data-history" in plan.url
    assert "module=2" in plan.url
    assert "instFamilyList=BTC-USDT" in plan.url
