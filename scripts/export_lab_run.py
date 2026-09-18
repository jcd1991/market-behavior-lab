#!/usr/bin/env python3
"""Export a Freqtrade backtest into the Market Behavior Lab contract."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

SCHEMA_VERSION = "1.0"
REDACT_KEYS = {"key", "secret", "password", "token", "jwt_secret_key", "api_key"}


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        timestamp = pd.Timestamp(value)
        return (timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")).isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=_json_default, allow_nan=False) + "\n", encoding="utf-8")


def _safe_config(config: dict[str, Any]) -> dict[str, Any]:
    def scrub(value: Any, key: str = "") -> Any:
        if key.lower() in REDACT_KEYS:
            return ""
        if key.lower() in {"config_files", "datadir", "exportdirectory", "userdir"}:
            if isinstance(value, list):
                return [Path(str(item)).name for item in value]
            return Path(str(value)).name if value else ""
        if isinstance(value, dict):
            return {k: scrub(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return scrub(config)


def _load_export(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            result_names = [n for n in archive.namelist() if n.endswith(".json") and not n.endswith("_config.json")]
            config_names = [n for n in archive.namelist() if n.endswith("_config.json")]
            if not result_names:
                raise ValueError("backtest archive does not contain a result JSON")
            result = json.loads(archive.read(result_names[0]))
            config = json.loads(archive.read(config_names[0])) if config_names else {}
            return result, config
    result = json.loads(path.read_text(encoding="utf-8"))
    config_path = path.with_name(path.stem + "_config.json")
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    return result, config


def _strategy_payload(result: dict[str, Any], strategy: str | None) -> tuple[str, dict[str, Any]]:
    strategies = result.get("strategy", {})
    if not isinstance(strategies, dict) or not strategies:
        raise ValueError("backtest result has no strategy payload")
    selected = strategy or next(iter(strategies))
    if selected not in strategies:
        raise ValueError(f"strategy {selected!r} not found in backtest result")
    return selected, strategies[selected]


def _pair_from_filename(path: Path) -> str | None:
    match = re.match(r"(?P<pair>[A-Z0-9]+_[A-Z0-9]+)(?:_[A-Z0-9]+)?-[^-]+(?:-[^.]+)?\.feather$", path.name)
    return match.group("pair").replace("_", "/") if match else None


def _load_candles(datadir: Path, pairs: list[str], timeframe: str, market_type: str) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    wanted = {p.split(":", 1)[0].replace("/", "_").upper(): p for p in pairs}
    for path in datadir.rglob(f"*-{timeframe}*.feather"):
        if path.name.endswith(("-mark.feather", "-index.feather", "-funding_rate.feather")):
            continue
        pair = _pair_from_filename(path)
        key = pair.replace("/", "_").upper() if pair else ""
        if key not in wanted:
            continue
        frame = pd.read_feather(path)
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(frame.columns):
            continue
        frame = frame[["date", "open", "high", "low", "close", "volume"]].copy()
        frame["timestamp"] = pd.to_datetime(frame.pop("date"), utc=True)
        frame["pair"] = wanted[key]
        frame["market_type"] = market_type
        frame["source"] = "freqtrade-exchange-data"
        rows.append(frame)
    if not rows:
        return pd.DataFrame(columns=["timestamp", "pair", "market_type", "open", "high", "low", "close", "volume", "source"])
    return pd.concat(rows, ignore_index=True).sort_values(["timestamp", "pair"])


def _normal_trade(trade: dict[str, Any], exchange: str, market_type: str) -> dict[str, Any]:
    return {
        "pair": trade.get("pair"), "side": "short" if trade.get("is_short") else "long",
        "open_time": trade.get("open_date"), "close_time": trade.get("close_date"),
        "entry_price": trade.get("open_rate"), "exit_price": trade.get("close_rate"),
        "amount": trade.get("amount"), "leverage": trade.get("leverage", 1.0),
        "fee_open": trade.get("fee_open"), "fee_close": trade.get("fee_close"),
        "profit_abs": trade.get("profit_abs"), "profit_ratio": trade.get("profit_ratio"),
        "exit_reason": trade.get("exit_reason"), "entry_tag": trade.get("enter_tag"),
        "exit_tag": trade.get("exit_tag") or trade.get("exit_reason"),
        "funding_fees": trade.get("funding_fees"), "exchange": exchange,
        "market_type": market_type, "source": "freqtrade-backtest",
    }


def _analysis_rows(backtest_export: Path, name: str, strategy: str) -> list[dict[str, Any]]:
    """Load Freqtrade's optional analysis pickle without making it a hard dependency."""
    try:
        from freqtrade.data.btanalysis.bt_fileutils import load_backtest_analysis_data

        payload = load_backtest_analysis_data(backtest_export, name)
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    strategy_payload = payload.get(strategy, {})
    if not isinstance(strategy_payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    regime_columns = {
        "regime_id", "base_regime", "composite_regime", "vol_regime", "confidence",
        "trend_dir", "atr_phase", "market_state", "liquidity_quality",
    }
    signal_columns = {
        "enter_long", "enter_short", "exit_long", "exit_short", "enter_tag", "exit_tag",
        "regime_id", "base_regime", "composite_regime", "confidence",
    }
    for pair, frame in strategy_payload.items():
        if not isinstance(frame, pd.DataFrame):
            continue
        columns = regime_columns if name in {"signals", "exited"} else signal_columns
        selected = [column for column in columns if column in frame.columns]
        if "date" not in frame.columns:
            continue
        for record in frame[["date", *selected]].where(pd.notna(frame), None).to_dict(orient="records"):
            row: dict[str, Any] = {"timestamp": record.pop("date"), "pair": pair, "source": "freqtrade-analysis"}
            row.update(record)
            if name == "signals":
                row["signal_type"] = "signal-candle"
            rows.append(row)
    return rows


def export_run(backtest_export: Path, datadir: Path, output: Path, strategy: str | None) -> Path:
    result, config = _load_export(backtest_export)
    strategy_name, payload = _strategy_payload(result, strategy)
    exchange = str(config.get("exchange", {}).get("name", "unknown"))
    market_type = "futures" if config.get("trading_mode") == "futures" else "spot"
    timeframe = str(config.get("timeframe", "unknown"))
    pairs = list(config.get("exchange", {}).get("pair_whitelist", []))
    trades = [_normal_trade(t, exchange, market_type) for t in payload.get("trades", [])]
    signal_rows = _analysis_rows(backtest_export, "signals", strategy_name)
    regime_rows = _analysis_rows(backtest_export, "signals", strategy_name)
    for trade in trades:
        signal_rows.extend([
            {"timestamp": trade["open_time"], "pair": trade["pair"], "action": "entry", "side": trade["side"], "tag": trade["entry_tag"], "source": "freqtrade-backtest"},
            {"timestamp": trade["close_time"], "pair": trade["pair"], "action": "exit", "side": trade["side"], "tag": trade["exit_tag"], "source": "freqtrade-backtest"},
        ])
    start_equity = float(config.get("dry_run_wallet", 0.0) or 0.0)
    equity = []
    running = start_equity
    for trade in sorted(trades, key=lambda t: str(t.get("close_time") or t.get("open_time") or "")):
        running += float(trade.get("profit_abs") or 0.0)
        equity.append({"timestamp": trade.get("close_time") or trade.get("open_time"), "equity": running})
    peak = start_equity
    drawdown = []
    for point in equity:
        peak = max(peak, float(point["equity"]))
        drawdown.append({"timestamp": point["timestamp"], "drawdown_abs": float(point["equity"]) - peak})

    output.mkdir(parents=True, exist_ok=True)
    candles = _load_candles(datadir, pairs, timeframe, market_type)
    candles.to_parquet(output / "candles.parquet", index=False, compression=None)
    _write_json(output / "trades.json", {"schema_version": SCHEMA_VERSION, "source": "freqtrade-backtest", "trades": trades})
    _write_json(output / "signals.json", {"schema_version": SCHEMA_VERSION, "source": "freqtrade-analysis", "signals": signal_rows or payload.get("signals", [])})
    _write_json(output / "regimes.json", {"schema_version": SCHEMA_VERSION, "source": "freqtrade-analysis", "regimes": regime_rows})
    _write_json(output / "metrics.json", {
        "schema_version": SCHEMA_VERSION, "source": "freqtrade-backtest",
        "summary": {"trade_count": len(trades), "profit_abs": sum(float(t.get("profit_abs") or 0.0) for t in trades)},
        "equity_curve": equity, "drawdown_curve": drawdown,
        "per_pair": {
            pair: {"trade_count": sum(1 for trade in trades if trade.get("pair") == pair), "profit_abs": sum(float(trade.get("profit_abs") or 0.0) for trade in trades if trade.get("pair") == pair)}
            for pair in sorted({str(trade.get("pair")) for trade in trades})
        },
        "per_regime": {
            str(regime): {"signal_count": sum(1 for row in regime_rows if row.get("composite_regime") == regime)}
            for regime in sorted({str(row.get("composite_regime")) for row in regime_rows if row.get("composite_regime")})
        },
    })
    _write_json(output / "run.json", {
        "schema_version": SCHEMA_VERSION, "run_id": output.name,
        "created_at": datetime.now(timezone.utc).isoformat(), "strategy": strategy_name,
        "exchange": exchange, "market_type": market_type, "timeframe": timeframe,
        "timerange": config.get("timerange"), "pairs": pairs,
        "quote_currency": config.get("stake_currency"),
        "settlement_currency": config.get("stake_currency") if market_type == "futures" else None,
        "data_provenance": "freqtrade-exchange-data",
        "config": _safe_config({k: v for k, v in config.items() if k not in {"exchange", "api_server", "telegram"}}),
        "warnings": ["No regime rows were present in the backtest export."] if not regime_rows else [],
    })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest-export", type=Path, required=True)
    parser.add_argument("--datadir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strategy")
    args = parser.parse_args()
    export_run(args.backtest_export, args.datadir, args.output, args.strategy)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
