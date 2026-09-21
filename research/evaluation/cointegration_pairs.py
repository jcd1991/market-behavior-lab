"""Build a versioned, venue-preserving cointegration diagnostic contract."""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd


def load_ohlcv(path: Path) -> pd.DataFrame:
    frame = pd.read_feather(path)
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    return frame.sort_values("date").drop_duplicates("date").set_index("date")


def pair_diagnostic(a: pd.DataFrame, b: pd.DataFrame, window: int = 240) -> dict:
    joined = pd.concat([a["close"].rename("a"), b["close"].rename("b")], axis=1).dropna()
    if len(joined) < window:
        return {"observations": int(len(joined)), "eligible": False, "reason": "insufficient_overlap"}
    y, x = np.log(joined["a"]), np.log(joined["b"])
    beta = float(x.rolling(window).cov(y).iloc[-1] / x.rolling(window).var().iloc[-1])
    residual = y - beta * x
    z = float((residual.iloc[-1] - residual.iloc[-window:].mean()) / residual.iloc[-window:].std())
    corr = float(y.iloc[-window:].corr(x.iloc[-window:]))
    lag = residual.shift(1).iloc[-window + 1:]
    delta = residual.diff().iloc[-window + 1:]
    slope = float(np.polyfit(lag.to_numpy(), delta.to_numpy(), 1)[0]) if len(lag) > 2 else 0.0
    half_life = float(-np.log(2) / slope) if slope < 0 else None
    return {"observations": int(len(joined)), "eligible": bool(corr >= 0.75 and half_life is not None and half_life > 0),
            "beta": beta, "residual_z": z, "correlation": corr, "half_life_bars": half_life}


def build_contract(data_dir: Path, pairs: list[str], venue: str, market_type: str,
                   timeframe: str, window: int = 240) -> dict:
    loaded = {pair: load_ohlcv(data_dir / f"{pair.replace('/', '_').replace(':', '_')}-{timeframe}.feather") for pair in pairs}
    rows = []
    for a, b in combinations(pairs, 2):
        rows.append({"pair_a": a, "pair_b": b, **pair_diagnostic(loaded[a], loaded[b], window)})
    return {"schema_version": "cointegration.v1", "source": "freqtrade-ohlcv", "venue": venue,
            "market_type": market_type, "timeframe": timeframe, "formation_window": window,
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "pairs": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--pairs", nargs="+", required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--market-type", default="spot")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--window", type=int, default=240)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_contract(args.data_dir, args.pairs, args.venue, args.market_type,
                                                    args.timeframe, args.window), indent=2) + "\n")


if __name__ == "__main__":
    main()
