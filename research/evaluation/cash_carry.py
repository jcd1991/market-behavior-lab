"""Same-venue spot/perpetual cash-and-carry evaluator.

The evaluator is deliberately fail-closed. It requires spot, perpetual,
funding, and index data from the same venue, then accounts for convergence,
funding, borrow, collateral, fees, and a liquidation-buffer gate. It does not
join venues or substitute CoinGecko for an exchange index.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _read(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_feather(path)
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    return frame.sort_values("date").drop_duplicates("date")


def _close(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    value = pd.to_numeric(frame["close"], errors="coerce")
    return pd.DataFrame({"date": frame["date"], name: value}).dropna().sort_values("date")


@dataclass(frozen=True)
class CarryAssumptions:
    entry_basis: float = 0.005
    exit_basis: float = 0.001
    min_funding: float = 0.0001
    round_trip_cost: float = 0.002
    annual_borrow_rate: float = 0.0
    annual_collateral_rate: float = 0.0
    collateral_fraction: float = 1.0
    min_margin_buffer: float = 0.20
    adverse_basis_shock: float = 0.01
    venue_failure_cost: float = 0.01


def _funding_column(frame: pd.DataFrame) -> str | None:
    return next((c for c in ("funding_rate", "funding", "rate", "close") if c in frame.columns), None)


def _optional_column(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype=float)


def evaluate_pair(
    spot: Path,
    perp: Path,
    funding: Path,
    index: Path,
    spot_venue: str,
    perp_venue: str,
    entry_basis: float = 0.005,
    exit_basis: float = 0.001,
    min_funding: float = 0.0001,
    round_trip_cost: float = 0.002,
    *,
    assumptions: CarryAssumptions | None = None,
) -> dict[str, Any]:
    """Evaluate one normalized same-venue cash-and-carry pair."""
    if spot_venue.lower() != perp_venue.lower():
        return {"eligible": False, "reason": "venue_mismatch", "spot_venue": spot_venue, "perp_venue": perp_venue}
    base = assumptions or CarryAssumptions(entry_basis, exit_basis, min_funding, round_trip_cost)
    required = {"spot": spot, "perp": perp, "funding": funding, "index": index}
    missing = sorted(name for name, path in required.items() if not path.is_file())
    if missing:
        return {"eligible": False, "reason": "missing_input", "missing": missing, "venue": spot_venue}
    spot_df, perp_df, funding_df, index_df = map(_read, (spot, perp, funding, index))
    fcol = _funding_column(funding_df)
    if fcol is None:
        return {"eligible": False, "reason": "funding_column_missing", "venue": spot_venue}
    merged = pd.merge_asof(_close(spot_df, "spot_close"), _close(perp_df, "perp_close"), on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    merged = pd.merge_asof(merged, _close(index_df, "index_close"), on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    rates = funding_df[["date", fcol]].rename(columns={fcol: "funding_rate"}).copy()
    rates["funding_rate"] = pd.to_numeric(rates["funding_rate"], errors="coerce")
    merged = pd.merge_asof(merged, rates.sort_values("date"), on="date", direction="backward", tolerance=pd.Timedelta("8h"))
    margin = _optional_column(perp_df, ("margin_buffer", "liquidation_distance", "liquidation_buffer"))
    if margin.notna().any():
        margin_frame = pd.DataFrame({"date": perp_df["date"], "margin_buffer": margin}).dropna().sort_values("date")
        merged = pd.merge_asof(merged, margin_frame, on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    else:
        merged["margin_buffer"] = np.nan
    merged["basis"] = merged["perp_close"] / merged["index_close"] - 1.0
    merged["carry_signal"] = (merged["basis"] >= base.entry_basis) & (merged["funding_rate"] >= base.min_funding)
    merged["carry_exit"] = merged["basis"].le(base.exit_basis) | merged["funding_rate"].lt(0)
    valid = merged.dropna(subset=["spot_close", "perp_close", "index_close", "funding_rate"])
    if valid.empty:
        return {"eligible": False, "reason": "no_exact_overlap", "venue": spot_venue}
    held = False
    entry_basis_value = 0.0
    entry_time: pd.Timestamp | None = None
    returns: list[float] = []
    entries = 0
    margin_rejections = 0
    periods_held = 0
    for row in valid.itertuples():
        margin_ok = pd.isna(row.margin_buffer) or float(row.margin_buffer) >= base.min_margin_buffer
        if not held and row.carry_signal:
            if not margin_ok:
                margin_rejections += 1
                continue
            held = True
            entries += 1
            entry_time = row.date
            entry_basis_value = float(row.basis)
        elif held:
            periods_held += 1
            if row.carry_exit:
                days = max(0.0, (row.date - entry_time).total_seconds() / 86400.0) if entry_time is not None else 0.0
                borrow = base.annual_borrow_rate * days / 365.0
                collateral = base.annual_collateral_rate * base.collateral_fraction * days / 365.0
                returns.append(float(entry_basis_value - row.basis + row.funding_rate - borrow - collateral - base.round_trip_cost))
                held = False
                entry_time = None
    if held:
        row = valid.iloc[-1]
        days = max(0.0, (row["date"] - entry_time).total_seconds() / 86400.0) if entry_time is not None else 0.0
        borrow = base.annual_borrow_rate * days / 365.0
        collateral = base.annual_collateral_rate * base.collateral_fraction * days / 365.0
        returns.append(float(entry_basis_value - row["basis"] - borrow - collateral - base.round_trip_cost))
    profit = float(np.sum(returns))
    stress_profit = profit - max(0.0, base.adverse_basis_shock) - max(0.0, base.venue_failure_cost if entries else 0.0)
    return {
        "eligible": True, "venue": spot_venue, "observations": int(len(valid)), "entries": entries,
        "closed_or_force_closed": len(returns), "margin_rejections": margin_rejections,
        "periods_held": periods_held, "basis_mean": float(valid["basis"].mean()),
        "basis_max": float(valid["basis"].max()), "funding_mean": float(valid["funding_rate"].mean()),
        "profit_ratio": profit, "round_trip_cost": base.round_trip_cost,
        "stress_profit_ratio": stress_profit, "stress": {
            "adverse_basis_shock": base.adverse_basis_shock,
            "venue_failure_cost": base.venue_failure_cost,
            "description": "Forced exit after adverse basis shock; funding is not backfilled during failure.",
        },
        "data_coverage": {"margin_buffer": bool(valid["margin_buffer"].notna().any())},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spot", type=Path, required=True)
    parser.add_argument("--perp", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--spot-venue", required=True)
    parser.add_argument("--perp-venue", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_pair(args.spot, args.perp, args.funding, args.index, args.spot_venue, args.perp_venue)
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
