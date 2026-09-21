"""Run a bounded mix-and-match matrix over compatible Freqtrade exports.

This is a research approximation, not a synchronized multi-strategy bot
simulation. Each Freqtrade export has its own wallet and open-trade limits;
the matrix weights realized trade PnL by sleeve and orders the resulting
closed-trade events by UTC close time. It is intended to identify promising
combinations for a later shared-wallet allocator.
"""

from __future__ import annotations

import argparse
import itertools
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Candidate:
    name: str
    path: Path
    venue: str
    market_type: str
    timeframe: str


def load_result(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".json") and "config" not in name]
        if not names:
            raise ValueError(f"no backtest JSON found in {path}")
        payload = json.loads(archive.read(names[0]))
    strategies = payload.get("strategy", {})
    if len(strategies) != 1:
        raise ValueError(f"expected one strategy in {path}, found {list(strategies)}")
    return next(iter(strategies.values()))


def candidate_from_export(path: Path, name: str | None = None) -> Candidate:
    result = load_result(path)
    trading_mode = result.get("trading_mode", "unknown")
    venue = result.get("exchange", "unknown")
    # Older Freqtrade exports do not repeat the exchange in the strategy
    # payload. The matrix CLI requires the caller to label those explicitly.
    return Candidate(
        name=name or result.get("strategy_name", path.stem),
        path=path,
        venue=venue,
        market_type=trading_mode,
        timeframe=result.get("timeframe", "unknown"),
    )


def summarize(
    candidates: list[Candidate],
    weights: list[float],
    starting_balance: float = 1000.0,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    if not candidates or len(candidates) != len(weights):
        raise ValueError("candidates and weights must be non-empty and the same length")
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("weights must sum to a positive value")

    events: list[pd.DataFrame] = []
    details = []
    for candidate, weight in zip(candidates, weights):
        result = load_result(candidate.path)
        trades = pd.DataFrame(result.get("trades", []))
        if trades.empty:
            continue
        trades["close_date"] = pd.to_datetime(trades.get("close_date"), utc=True, errors="coerce")
        trades["profit_abs"] = pd.to_numeric(trades.get("profit_abs", 0.0), errors="coerce").fillna(0.0)
        trades = trades.dropna(subset=["close_date"])
        if start:
            trades = trades[trades["close_date"] >= pd.Timestamp(start, tz="UTC")]
        if end:
            trades = trades[trades["close_date"] < pd.Timestamp(end, tz="UTC")]
        if trades.empty:
            continue
        scale = float(weight) / total_weight
        events.append(pd.DataFrame({
            "close_date": trades["close_date"],
            "profit_abs": trades["profit_abs"] * scale,
            "sleeve": candidate.name,
        }))
        details.append({
            "name": candidate.name,
            "weight": weight,
            "trades": int(len(trades)),
            "raw_profit_abs": float(trades["profit_abs"].sum()),
        })

    if not events:
        return {"profit_pct": 0.0, "trades": 0, "max_drawdown_pct": 0.0, "sleeves": details}
    frame = pd.concat(events, ignore_index=True).sort_values(["close_date", "sleeve"])
    equity = starting_balance + frame["profit_abs"].cumsum()
    drawdown = equity / equity.cummax() - 1.0
    profit = float(frame["profit_abs"].sum())
    return {
        "profit_abs": profit,
        "profit_pct": profit / starting_balance * 100.0,
        "trades": int(len(frame)),
        "max_drawdown_pct": float(abs(drawdown.min()) * 100.0),
        "first_close": frame["close_date"].iloc[0].isoformat(),
        "last_close": frame["close_date"].iloc[-1].isoformat(),
        "sleeves": details,
    }


def matrix(
    candidates: list[Candidate],
    max_size: int = 3,
    starting_balance: float = 1000.0,
    start: str | None = None,
    end: str | None = None,
) -> list[dict]:
    if not candidates:
        return []
    # Mixing venues, market types, or timeframes would create false precision.
    compatible = [c for c in candidates if c.venue == "binanceus" and c.market_type == "spot"]
    rows = []
    for size in range(1, min(max_size, len(compatible)) + 1):
        for combo in itertools.combinations(compatible, size):
            result = summarize(list(combo), [1.0] * size, starting_balance, start, end)
            rows.append({"combination": [c.name for c in combo], **result})
    return sorted(rows, key=lambda row: (row["profit_pct"], -row["max_drawdown_pct"]), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", action="append", required=True, help="name:path:venue:market_type")
    parser.add_argument("--max-size", type=int, default=3)
    parser.add_argument("--start", help="inclusive UTC close-date filter")
    parser.add_argument("--end", help="exclusive UTC close-date filter")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    candidates = []
    for value in args.candidate:
        name, path, venue, market_type = value.split(":", 3)
        result = load_result(Path(path))
        candidates.append(Candidate(name, Path(path), venue, market_type, result.get("timeframe", "unknown")))
    payload = {
        "method": "equal-weight closed-trade sleeve approximation",
        "window": {"start": args.start, "end": args.end},
        "rows": matrix(candidates, args.max_size, start=args.start, end=args.end),
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
