"""Summarize Freqtrade trades by UTC session and weekend status."""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def load_trades(path: Path, strategy: str) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".json") and "config" not in name)
        payload = json.loads(archive.read(member))
    return list(payload.get("strategy", {}).get(strategy, {}).get("trades", []) or [])


def session_for_hour(hour: int) -> str:
    if 13 <= hour < 20:
        return "us"
    if 7 <= hour < 13:
        return "europe"
    return "asia_or_overnight"


def summarize(trades: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        raw = trade.get("open_date") or trade.get("open_date_utc")
        if not raw:
            continue
        timestamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        profit = float(trade.get("profit_abs", 0.0) or 0.0)
        groups[session_for_hour(timestamp.hour)].append(profit)
        groups["weekend" if timestamp.weekday() >= 5 else "weekday"].append(profit)
    return {
        name: {
            "trades": float(len(pnls)),
            "profit_abs": float(sum(pnls)),
            "win_rate_pct": float(100.0 * sum(1 for pnl in pnls if pnl > 0) / len(pnls)) if pnls else 0.0,
        }
        for name, pnls in sorted(groups.items())
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--strategy", default="RegimeRouted")
    args = parser.parse_args()
    print(json.dumps(summarize(load_trades(args.input, args.strategy)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
