"""Causal two-leg cointegration book simulator.

Unlike the Freqtrade signal strategy, this evaluator opens both legs at the
same timestamp and sizes the reference leg from the rolling hedge beta.  It
is intentionally an offline research tool: Freqtrade's one-position strategy
interface cannot guarantee synchronized hedge execution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_ohlcv(path: Path) -> pd.DataFrame:
    frame = pd.read_feather(path)
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    return frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date").set_index("date")


def _features(joined: pd.DataFrame, window: int) -> pd.DataFrame:
    y = np.log(pd.to_numeric(joined["asset_close"], errors="coerce").replace(0, np.nan))
    x = np.log(pd.to_numeric(joined["reference_close"], errors="coerce").replace(0, np.nan))
    beta = (y.rolling(window).cov(x) / x.rolling(window).var().replace(0, np.nan)).clip(0.05, 5.0)
    residual = y - beta * x
    mean = residual.rolling(window).mean()
    std = residual.rolling(window).std().replace(0, np.nan)
    lag = residual.shift(1)
    delta = residual.diff()
    slope = delta.rolling(window).cov(lag) / lag.rolling(window).var().replace(0, np.nan)
    half_life = (-np.log(2.0) / slope).where(slope < 0)
    return pd.DataFrame(
        {
            "beta": beta,
            "z": (residual - mean) / std,
            "corr": y.rolling(window).corr(x),
            "half_life": half_life,
        },
        index=joined.index,
    )


def _max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1.0).min() * -100.0)


def simulate_pair(
    asset: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    venue: str,
    window: int = 240,
    entry_z: float = 1.8,
    exit_z: float = 0.35,
    min_corr: float = 0.75,
    max_half_life: float = 120.0,
    round_trip_cost: float = 0.002,
) -> dict:
    joined = pd.concat(
        [asset["close"].rename("asset_close"), reference["close"].rename("reference_close")], axis=1
    ).dropna()
    if len(joined) < window + 2:
        return {"eligible": False, "reason": "insufficient_overlap", "observations": int(len(joined)), "venue": venue}

    features = _features(joined, int(window))
    asset_returns = joined["asset_close"].pct_change().fillna(0.0)
    reference_returns = joined["reference_close"].pct_change().fillna(0.0)
    equity = 1.0
    state = 0
    beta_weight = 0.0
    entry_count = 0
    closed_count = 0
    returns: list[float] = []
    equity_curve = [equity]

    for i in range(1, len(joined)):
        if state:
            # state +1: long asset / short reference; state -1 is the reverse.
            portfolio_return = state * (
                (1.0 - beta_weight) * float(asset_returns.iloc[i])
                - beta_weight * float(reference_returns.iloc[i])
            )
            equity *= max(0.0, 1.0 + portfolio_return)

        row = features.iloc[i]
        valid = (
            pd.notna(row["z"])
            and pd.notna(row["corr"])
            and pd.notna(row["half_life"])
            and float(row["corr"]) >= min_corr
            and 0.0 < float(row["half_life"]) <= max_half_life
        )
        z = float(row["z"]) if pd.notna(row["z"]) else np.nan
        if state and ((abs(z) <= exit_z) or not valid):
            equity *= max(0.0, 1.0 - round_trip_cost / 2.0)
            state = 0
            beta_weight = 0.0
            closed_count += 1
        elif not state and valid and abs(z) >= entry_z:
            state = 1 if z < 0 else -1
            beta = min(5.0, max(0.05, abs(float(row["beta"]))))
            beta_weight = beta / (1.0 + beta)
            equity *= max(0.0, 1.0 - round_trip_cost / 2.0)
            entry_count += 1
        equity_curve.append(equity)

    if state:
        equity *= max(0.0, 1.0 - round_trip_cost / 2.0)
        closed_count += 1
        equity_curve[-1] = equity

    curve = pd.Series(equity_curve, index=joined.index)
    return {
        "eligible": True,
        "venue": venue,
        "observations": int(len(joined)),
        "entries": entry_count,
        "closed_or_force_closed": closed_count,
        "profit_ratio": float(equity - 1.0),
        "profit_pct": float((equity - 1.0) * 100.0),
        "max_drawdown_pct": _max_drawdown(curve),
        "round_trip_cost": float(round_trip_cost),
        "window": int(window),
        "entry_z": float(entry_z),
        "exit_z": float(exit_z),
        "min_corr": float(min_corr),
        "max_half_life": float(max_half_life),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--window", type=int, default=240)
    parser.add_argument("--entry-z", type=float, default=1.8)
    parser.add_argument("--exit-z", type=float, default=0.35)
    parser.add_argument("--min-corr", type=float, default=0.75)
    parser.add_argument("--max-half-life", type=float, default=120.0)
    parser.add_argument("--round-trip-cost", type=float, default=0.002)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = simulate_pair(
        load_ohlcv(args.asset),
        load_ohlcv(args.reference),
        venue=args.venue,
        window=args.window,
        entry_z=args.entry_z,
        exit_z=args.exit_z,
        min_corr=args.min_corr,
        max_half_life=args.max_half_life,
        round_trip_cost=args.round_trip_cost,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
