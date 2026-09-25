"""Fail-closed same-venue spot/perpetual cash-and-carry evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _read(path: Path) -> pd.DataFrame:
    frame = pd.read_feather(path)
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    return frame.sort_values("date").drop_duplicates("date")


def _close(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    value = pd.to_numeric(frame["close"], errors="coerce")
    return pd.DataFrame({"date": frame["date"], name: value}).dropna().sort_values("date")


def evaluate_pair(spot: Path, perp: Path, funding: Path, index: Path, spot_venue: str, perp_venue: str,
                  entry_basis: float = 0.005, exit_basis: float = 0.001, min_funding: float = 0.0001,
                  round_trip_cost: float = 0.002) -> dict:
    if spot_venue.lower() != perp_venue.lower():
        return {"eligible": False, "reason": "venue_mismatch", "spot_venue": spot_venue, "perp_venue": perp_venue}
    required = {"spot": spot, "perp": perp, "funding": funding, "index": index}
    missing = sorted(name for name, path in required.items() if not path.is_file())
    if missing:
        return {"eligible": False, "reason": "missing_input", "missing": missing, "venue": spot_venue}
    spot_df, perp_df, funding_df, index_df = map(_read, (spot, perp, funding, index))
    fcol = next((c for c in ("funding_rate", "funding", "rate", "close") if c in funding_df.columns), None)
    if fcol is None:
        return {"eligible": False, "reason": "funding_column_missing"}
    merged = pd.merge_asof(_close(spot_df, "spot_close"), _close(perp_df, "perp_close"), on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    merged = pd.merge_asof(merged, _close(index_df, "index_close"), on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    rates = funding_df[["date", fcol]].rename(columns={fcol: "funding_rate"}).copy()
    rates["funding_rate"] = pd.to_numeric(rates["funding_rate"], errors="coerce")
    merged = pd.merge_asof(merged, rates.sort_values("date"), on="date", direction="backward", tolerance=pd.Timedelta("8h"))
    merged["basis"] = merged["perp_close"] / merged["index_close"] - 1.0
    merged["carry_signal"] = (merged["basis"] >= entry_basis) & (merged["funding_rate"] >= min_funding)
    merged["carry_exit"] = merged["basis"].le(exit_basis) | merged["funding_rate"].lt(0)
    valid = merged.dropna(subset=["spot_close", "perp_close", "index_close", "funding_rate"])
    if valid.empty:
        return {"eligible": False, "reason": "no_exact_overlap", "venue": spot_venue}
    held = False
    entry_basis_value = 0.0
    returns = []
    entries = 0
    for row in valid.itertuples():
        if not held and row.carry_signal:
            held = True
            entries += 1
            entry_basis_value = float(row.basis)
        elif held and row.carry_exit:
            returns.append(float(entry_basis_value - row.basis + row.funding_rate - round_trip_cost))
            held = False
    if held:
        row = valid.iloc[-1]
        returns.append(float(entry_basis_value - row.basis + row.funding_rate - round_trip_cost))
    result = {
        "eligible": True,
        "venue": spot_venue,
        "observations": int(len(valid)),
        "entries": entries,
        "closed_or_force_closed": len(returns),
        "basis_mean": float(valid["basis"].mean()),
        "basis_max": float(valid["basis"].max()),
        "funding_mean": float(valid["funding_rate"].mean()),
        "profit_ratio": float(np.sum(returns)),
        "round_trip_cost": round_trip_cost,
    }
    return result


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
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
