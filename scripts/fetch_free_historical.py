#!/usr/bin/env python3
"""Fetch bounded, credential-free historical crypto data.

The command creates ignored local files under user_data/data/historical/raw.
It supports venue-native public archives/APIs from Binance, OKX, Kraken,
BitMEX, Tardis' public first-of-month datasets, and Coin Metrics Community
coverage/data endpoints. It does not merge providers or claim that a raw
download is Freqtrade execution truth.

Examples:

  Binance official archive (checksummed monthly 1-minute spot candles):
    python scripts/fetch_free_historical.py binance \
      --market-type spot --dataset klines --symbol BTCUSDT --interval 1m \
      --month 2026-08 --verify-checksum

  OKX public historical candles and funding:
    python scripts/fetch_free_historical.py okx \
      --dataset history-candles --inst-id BTC-USDT-SWAP --bar 1m --limit 100

  BitMEX public daily trades:
    python scripts/fetch_free_historical.py bitmex \
      --dataset trade --date 2015-01-01

  Tardis public first-of-month dataset:
    python scripts/fetch_free_historical.py tardis \
      --exchange deribit --dataset trades --date 2025-03-01 \
      --symbol BTC-PERPETUAL
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile


SCHEMA_VERSION = "free-historical.v1"
DEFAULT_ROOT = Path("user_data/data/historical/raw")
USER_AGENT = "market-behavior-lab-free-data/0.1"


@dataclass(frozen=True)
class FetchPlan:
    provider: str
    dataset: str
    url: str
    output_name: str
    requested: Mapping[str, Any]
    source_kind: str


def safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"date must be YYYY-MM-DD: {value}") from exc
    return value


def parse_month(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise ValueError(f"month must be YYYY-MM: {value}") from exc
    return value


def requested_args(args: argparse.Namespace) -> dict[str, Any]:
    """Convert argparse values into manifest-safe JSON values."""

    result: dict[str, Any] = {}
    for key, value in vars(args).items():
        result[key] = str(value) if isinstance(value, Path) else value
    return result


def http_get(url: str, *, timeout: int = 120) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get("Content-Type", "")


def binance_plan(args: argparse.Namespace) -> FetchPlan:
    symbol = args.symbol.upper()
    if not re.fullmatch(r"[A-Z0-9]+", symbol):
        raise ValueError("Binance symbol must be an exchange symbol such as BTCUSDT")
    if args.market_type == "spot":
        root = "https://data.binance.vision/data/spot"
    else:
        root = f"https://data.binance.vision/data/futures/{args.futures_market}"
    dataset = args.dataset
    if args.month:
        period = parse_month(args.month)
        period_path = f"monthly/{dataset}/{symbol}"
    elif args.date:
        period = parse_date(args.date)
        period_path = f"daily/{dataset}/{symbol}"
    else:
        raise ValueError("Binance requires --month or --date")
    if dataset == "klines":
        if not args.interval:
            raise ValueError("Binance klines require --interval")
        period_path += f"/{args.interval}"
        filename = f"{symbol}-{args.interval}-{period}.zip"
    else:
        filename = f"{symbol}-{dataset}-{period}.zip"
    url = f"{root}/{period_path}/{filename}"
    return FetchPlan(
        "binance",
        dataset,
        url,
        filename,
        requested_args(args),
        "venue-native-public-archive",
    )


def okx_plan(args: argparse.Namespace) -> FetchPlan:
    endpoint_map = {
        "history-candles": "market/history-candles",
        "history-trades": "market/history-trades",
        "funding-rate-history": "public/funding-rate-history",
        "open-interest": "public/open-interest",
        "mark-price": "public/mark-price",
        "index-candles": "market/index-candles",
        "history-index-candles": "market/history-index-candles",
        "market-data-history": "public/market-data-history",
    }
    endpoint = endpoint_map[args.dataset]
    params: dict[str, str] = {}
    if args.inst_id:
        params["instId"] = args.inst_id
    if args.bar:
        params["bar"] = args.bar
    if args.limit:
        params["limit"] = str(args.limit)
    if args.after:
        params["after"] = args.after
    if args.before:
        params["before"] = args.before
    if args.inst_type:
        params["instType"] = args.inst_type
    if args.module:
        params["module"] = str(args.module)
    if args.inst_id_list:
        params["instIdList"] = args.inst_id_list
    if args.inst_family_list:
        params["instFamilyList"] = args.inst_family_list
    if args.date_aggr_type:
        params["dateAggrType"] = args.date_aggr_type
    if args.begin:
        params["begin"] = args.begin
    if args.end:
        params["end"] = args.end
    if not params:
        raise ValueError("OKX requires at least --inst-id or --inst-type")
    query = urlencode(params)
    module_suffix = f"-module{args.module}" if args.module else ""
    name = f"{safe_component(args.dataset)}{module_suffix}-{safe_component(args.inst_id or args.inst_type or args.inst_family_list or 'query')}.json"
    return FetchPlan(
        "okx",
        args.dataset,
        f"https://www.okx.com/api/v5/{endpoint}?{query}",
        name,
        requested_args(args),
        "venue-native-public-api",
    )


def kraken_plan(args: argparse.Namespace) -> FetchPlan:
    if args.quarter:
        if not re.fullmatch(r"20\d{2}Q[1-4]", args.quarter):
            raise ValueError("Kraken quarter must look like 2026Q2")
        filename = f"Kraken_Trades_{args.quarter}.zip"
        url = f"https://assets.kraken.com/marketing/institutions/{filename}"
        dataset = "quarterly-trades-archive"
        source_kind = "venue-native-public-archive"
    else:
        if not args.pair:
            raise ValueError("Kraken REST trades require --pair")
        params = {"pair": args.pair}
        if args.since:
            params["since"] = args.since
        filename = f"trades-{safe_component(args.pair)}.json"
        url = "https://api.kraken.com/0/public/Trades?" + urlencode(params)
        dataset = "trades"
        source_kind = "venue-native-public-api-bounded-page"
    return FetchPlan("kraken", dataset, url, filename, requested_args(args), source_kind)


def bitmex_plan(args: argparse.Namespace) -> FetchPlan:
    date = parse_date(args.date).replace("-", "")
    filename = f"{date}.csv.gz"
    url = f"https://s3-eu-west-1.amazonaws.com/public.bitmex.com/data/{args.dataset}/{filename}"
    return FetchPlan(
        "bitmex",
        args.dataset,
        url,
        filename,
        requested_args(args),
        "venue-native-public-archive",
    )


def tardis_plan(args: argparse.Namespace) -> FetchPlan:
    date = parse_date(args.date)
    symbol = args.symbol or args.group
    if not symbol:
        raise ValueError("Tardis requires --symbol or --group")
    year, month, day = date.split("-")
    filename = f"{safe_component(symbol)}.csv.gz"
    url = f"https://datasets.tardis.dev/v1/{args.exchange}/{args.dataset}/{year}/{month}/{day}/{filename}"
    return FetchPlan(
        "tardis",
        args.dataset,
        url,
        filename,
        requested_args(args),
        "venue-native-public-dataset-sample",
    )


def coinmetrics_plan(args: argparse.Namespace) -> FetchPlan:
    endpoint = args.dataset
    if endpoint.startswith("catalog-"):
        endpoint = "catalog-all/" + endpoint.removeprefix("catalog-")
        params = {"limit": str(args.limit or 100)}
        filename = f"catalog-{safe_component(args.dataset.removeprefix('catalog-'))}.json"
        source_kind = "coverage-catalog-community"
    else:
        endpoint = "timeseries/" + endpoint.removeprefix("timeseries-")
        if not args.market or not args.start or not args.end:
            raise ValueError("Coin Metrics time series requires --market, --start, and --end")
        params = {
            "markets": args.market,
            "start_time": args.start,
            "end_time": args.end,
        }
        if args.frequency:
            params["frequency"] = args.frequency
        if args.page_size:
            params["page_size"] = str(args.page_size)
        filename = f"{safe_component(args.market)}-{safe_component(args.dataset)}.json"
        source_kind = "normalized-community-api"
    return FetchPlan(
        "coinmetrics",
        args.dataset,
        "https://community-api.coinmetrics.io/v4/" + endpoint + "?" + urlencode(params),
        filename,
        requested_args(args),
        source_kind,
    )


def plan_from_args(args: argparse.Namespace) -> FetchPlan:
    if args.provider == "binance":
        return binance_plan(args)
    if args.provider == "okx":
        return okx_plan(args)
    if args.provider == "kraken":
        return kraken_plan(args)
    if args.provider == "bitmex":
        return bitmex_plan(args)
    if args.provider == "tardis":
        return tardis_plan(args)
    if args.provider == "coinmetrics":
        return coinmetrics_plan(args)
    raise ValueError(f"unsupported provider: {args.provider}")


def validate_download(path: Path, plan: FetchPlan, content_type: str) -> None:
    if path.suffix == ".zip":
        if not zipfile.is_zipfile(path):
            raise ValueError(f"download is not a valid zip archive: {path}")
    if path.suffix == ".gz":
        try:
            with gzip.open(path, "rb") as stream:
                stream.read(1)
        except OSError as exc:
            raise ValueError(f"download is not a valid gzip archive: {path}") from exc
    if plan.provider in {"coinmetrics", "okx", "kraken"} and path.suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"download is not valid JSON: {path}") from exc
        if plan.provider == "okx" and payload.get("code") not in (None, "0", 0):
            raise ValueError(f"OKX API returned code {payload.get('code')}: {payload.get('msg', '')}")
        if plan.provider == "kraken" and payload.get("error"):
            raise ValueError(f"Kraken API returned errors: {payload['error']}")
        if plan.provider == "coinmetrics" and payload.get("error"):
            raise ValueError(f"Coin Metrics API returned an error: {payload['error']}")
    if content_type.startswith("text/html"):
        raise ValueError(f"provider returned HTML instead of data: {content_type}")


def download_okx_links(query_path: Path, output_root: Path) -> list[dict[str, Any]]:
    """Download OKX files returned by the public historical-data query."""

    payload = json.loads(query_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for batch in payload.get("data", []):
        for detail in batch.get("details", []):
            for group in detail.get("groupDetails", []):
                url = group.get("url")
                filename = group.get("filename")
                if not url or not filename:
                    continue
                destination = output_root / "okx" / "market-data-history" / safe_component(filename)
                destination.parent.mkdir(parents=True, exist_ok=True)
                part = destination.with_suffix(destination.suffix + ".part")
                record: dict[str, Any] = {"url": url, "filename": filename, "path": str(destination)}
                try:
                    data, content_type = http_get(url)
                    part.write_bytes(data)
                    part.replace(destination)
                    if filename.endswith(".zip") and not zipfile.is_zipfile(destination):
                        raise ValueError("OKX historical file is not a valid zip archive")
                    if filename.endswith(".gz"):
                        with gzip.open(destination, "rb") as stream:
                            stream.read(1)
                    record.update({
                        "status": "complete",
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "content_type": content_type,
                    })
                except (HTTPError, URLError, OSError, ValueError) as exc:
                    if part.exists():
                        part.unlink()
                    record.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
                results.append(record)
    return results


def fetch_plan(plan: FetchPlan, output_root: Path, *, verify_checksum: bool = False) -> Path:
    directory = output_root / safe_component(plan.provider) / safe_component(plan.dataset)
    directory.mkdir(parents=True, exist_ok=True)
    data_path = directory / plan.output_name
    manifest_path = directory / (plan.output_name + ".manifest.json")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "provider": plan.provider,
        "dataset": plan.dataset,
        "source_url": plan.url,
        "source_kind": plan.source_kind,
        "requested": dict(plan.requested),
        "retrieved_at": utc_now(),
        "execution_truth": False,
        "status": "running",
        "path": str(data_path),
        "errors": [],
    }
    part_path = data_path.with_suffix(data_path.suffix + ".part")
    try:
        payload, content_type = http_get(plan.url)
        part_path.write_bytes(payload)
        part_path.replace(data_path)
        validate_download(data_path, plan, content_type)
        result.update(
            {
                "status": "complete",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "content_type": content_type,
            }
        )
        if verify_checksum and plan.provider == "binance" and data_path.suffix == ".zip":
            checksum_payload, _ = http_get(plan.url + ".CHECKSUM")
            checksum_text = checksum_payload.decode("utf-8", errors="replace")
            expected = checksum_text.split()[0]
            actual = result["sha256"]
            result["checksum"] = {"expected": expected, "actual": actual, "match": expected == actual}
            if expected != actual:
                raise ValueError("Binance archive checksum mismatch")
    except (HTTPError, URLError, OSError, ValueError) as exc:
        if part_path.exists():
            part_path.unlink()
        result["status"] = "error"
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if result["status"] != "complete":
        raise RuntimeError(result["errors"][0])
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="provider", required=True)

    binance = subparsers.add_parser("binance")
    binance.add_argument("--market-type", choices=("spot", "futures"), default="spot")
    binance.add_argument("--futures-market", choices=("um", "cm"), default="um")
    binance.add_argument("--dataset", choices=("klines", "aggTrades", "trades"), required=True)
    binance.add_argument("--symbol", required=True)
    binance.add_argument("--interval")
    binance.add_argument("--month")
    binance.add_argument("--date")
    binance.add_argument("--verify-checksum", action="store_true")

    okx = subparsers.add_parser("okx")
    okx.add_argument("--dataset", choices=("history-candles", "history-trades", "funding-rate-history", "open-interest", "mark-price", "index-candles", "history-index-candles", "market-data-history"), required=True)
    okx.add_argument("--inst-id")
    okx.add_argument("--inst-type")
    okx.add_argument("--bar")
    okx.add_argument("--limit", type=int)
    okx.add_argument("--after")
    okx.add_argument("--before")
    okx.add_argument("--module", type=int, choices=(1, 2, 3, 4, 5, 6, 11))
    okx.add_argument("--inst-id-list")
    okx.add_argument("--inst-family-list")
    okx.add_argument("--date-aggr-type", choices=("daily", "monthly"))
    okx.add_argument("--begin")
    okx.add_argument("--end")
    okx.add_argument("--download-links", action="store_true")

    kraken = subparsers.add_parser("kraken")
    kraken.add_argument("--quarter")
    kraken.add_argument("--pair")
    kraken.add_argument("--since")

    bitmex = subparsers.add_parser("bitmex")
    bitmex.add_argument("--dataset", choices=("trade", "quote"), required=True)
    bitmex.add_argument("--date", required=True)

    tardis = subparsers.add_parser("tardis")
    tardis.add_argument("--exchange", required=True)
    tardis.add_argument("--dataset", required=True)
    tardis.add_argument("--date", required=True)
    tardis.add_argument("--symbol")
    tardis.add_argument("--group")

    coinmetrics = subparsers.add_parser("coinmetrics")
    coinmetrics.add_argument("--dataset", required=True, help="catalog-market-orderbooks or timeseries-market-candles")
    coinmetrics.add_argument("--market")
    coinmetrics.add_argument("--start")
    coinmetrics.add_argument("--end")
    coinmetrics.add_argument("--frequency")
    coinmetrics.add_argument("--page-size", type=int)
    coinmetrics.add_argument("--limit", type=int)

    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        plan = plan_from_args(args)
        manifest = fetch_plan(plan, args.output_root, verify_checksum=getattr(args, "verify_checksum", False))
        if args.provider == "okx" and getattr(args, "download_links", False):
            query_path = manifest.parent / manifest.name.removesuffix(".manifest.json")
            links = download_okx_links(query_path, args.output_root)
            query_manifest = json.loads(manifest.read_text(encoding="utf-8"))
            query_manifest["downloaded_links"] = links
            manifest.write_text(json.dumps(query_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (ValueError, RuntimeError) as exc:
        print(f"free historical fetch failed: {exc}", file=sys.stderr)
        return 2
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
