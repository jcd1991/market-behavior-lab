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
    source = next((column for column in ("close", "index_close", "mark_close", "price") if column in frame.columns), None)
    if source is None:
        raise ValueError("price frame must contain close, index_close, mark_close, or price")
    value = pd.to_numeric(frame[source], errors="coerce")
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
    require_margin_buffer: bool = False


def _funding_column(frame: pd.DataFrame) -> str | None:
    return next((c for c in ("funding_rate", "funding", "rate", "close") if c in frame.columns), None)


def _optional_column(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype=float)


def _load_inputs(spot: Path, perp: Path, funding: Path, index: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required = {"spot": spot, "perp": perp, "funding": funding, "index": index}
    missing = sorted(name for name, path in required.items() if not path.is_file())
    if missing:
        raise FileNotFoundError(",".join(missing))
    return tuple(_read(path) for path in (spot, perp, funding, index))  # type: ignore[return-value]


def _manifest(path: Path) -> dict[str, Any] | None:
    """Read the sidecar provenance manifest when one exists."""

    manifest_path = Path(f"{path}.manifest.json")
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _manifest_venue(manifest: dict[str, Any] | None) -> str | None:
    if not manifest:
        return None
    explicit = manifest.get("venue")
    if explicit:
        return str(explicit).lower()
    source = str(manifest.get("source", "")).lower()
    for candidate in ("binance-global", "binanceus", "coinbase", "okx", "kraken"):
        if candidate in source:
            return candidate
    return None


def audit_same_venue_inputs(
    spot: Path,
    perp: Path,
    funding: Path,
    index: Path,
    venue: str,
    *,
    min_overlap_days: float = 90.0,
    min_funding_events: int = 90,
    require_margin_buffer: bool = True,
) -> dict[str, Any]:
    """Audit whether a carry dataset is complete enough for promotion.

    The ordinary evaluator remains available for short diagnostics.  This
    stricter audit is the promotion gate: every leg must exist, carry an
    identifiable venue, overlap for a meaningful period, include enough
    funding events, and provide margin/liquidation observations.
    """

    paths = {"spot": spot, "perp": perp, "funding": funding, "index": index}
    missing = sorted(name for name, path in paths.items() if not path.is_file())
    requirements = {
        "min_overlap_days": min_overlap_days,
        "min_funding_events": min_funding_events,
        "require_margin_buffer": require_margin_buffer,
    }
    if missing:
        return {"eligible": False, "reason": "missing_input", "missing": missing, "venue": venue, "requirements": requirements}

    manifests = {name: _manifest(path) for name, path in paths.items()}
    expected_venue = venue.lower()
    provenance_errors = []
    for name, manifest in manifests.items():
        observed = _manifest_venue(manifest)
        if observed is None:
            provenance_errors.append(f"{name}:venue_provenance_missing")
        elif observed != expected_venue:
            provenance_errors.append(f"{name}:venue_mismatch:{observed}")

    frames = {name: _read(path) for name, path in paths.items()}
    overlap_start = max(frame["date"].min() for frame in frames.values())
    overlap_end = min(frame["date"].max() for frame in frames.values())
    overlap_days = max(0.0, (overlap_end - overlap_start).total_seconds() / 86400.0)
    funding_frame = frames["funding"]
    funding_col = _funding_column(funding_frame)
    funding_events = 0
    if funding_col is not None:
        funding_events = int(
            funding_frame["date"].between(overlap_start, overlap_end, inclusive="both").sum()
        )
    margin_col = next(
        (column for column in ("margin_buffer", "liquidation_distance", "liquidation_buffer") if column in frames["perp"].columns),
        None,
    )
    failures = list(provenance_errors)
    if overlap_days < min_overlap_days:
        failures.append("overlap_too_short")
    if funding_col is None:
        failures.append("funding_column_missing")
    elif funding_events < min_funding_events:
        failures.append("funding_history_too_short")
    if require_margin_buffer and margin_col is None:
        failures.append("margin_buffer_missing")
    return {
        "eligible": not failures,
        "reason": "ok" if not failures else "coverage_gate_failed",
        "venue": venue,
        "failures": failures,
        "requirements": requirements,
        "coverage": {
            "overlap_start": overlap_start,
            "overlap_end": overlap_end,
            "overlap_days": overlap_days,
            "funding_events": funding_events,
            "margin_buffer_available": margin_col is not None,
            "rows": {name: int(len(frame)) for name, frame in frames.items()},
        },
        "provenance": {
            name: {
                "manifest_present": manifests[name] is not None,
                "venue": _manifest_venue(manifests[name]),
                "source": manifests[name].get("source") if manifests[name] else None,
                "pair": manifests[name].get("pair") if manifests[name] else None,
            }
            for name in paths
        },
    }


def evaluate_frames(
    spot_df: pd.DataFrame,
    perp_df: pd.DataFrame,
    funding_df: pd.DataFrame,
    index_df: pd.DataFrame,
    spot_venue: str,
    *,
    assumptions: CarryAssumptions | None = None,
) -> dict[str, Any]:
    """Evaluate already-loaded same-venue inputs for tuning and split tests."""
    base = assumptions or CarryAssumptions()
    fcol = _funding_column(funding_df)
    if fcol is None:
        return {"eligible": False, "reason": "funding_column_missing", "venue": spot_venue}
    merged = pd.merge_asof(_close(spot_df, "spot_close"), _close(perp_df, "perp_close"), on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    merged = pd.merge_asof(merged, _close(index_df, "index_close"), on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    rates = funding_df[["date", fcol]].rename(columns={fcol: "funding_rate"}).copy()
    rates["funding_rate"] = pd.to_numeric(rates["funding_rate"], errors="coerce")
    rates = rates.dropna(subset=["date", "funding_rate"]).sort_values("date")
    merged = pd.merge_asof(merged, rates, on="date", direction="backward", tolerance=pd.Timedelta("8h"))
    margin = _optional_column(perp_df, ("margin_buffer", "liquidation_distance", "liquidation_buffer"))
    if margin.notna().any():
        margin_frame = pd.DataFrame({"date": perp_df["date"], "margin_buffer": margin}).dropna().sort_values("date")
        merged = pd.merge_asof(merged, margin_frame, on="date", direction="backward", tolerance=pd.Timedelta("2h"))
    else:
        merged["margin_buffer"] = np.nan
    # The executable cash-and-carry basis is perp versus the spot leg.  The
    # index remains a required venue-matched oracle for validation and risk,
    # but it is not silently substituted for the traded spot price.
    merged["basis"] = merged["perp_close"] / merged["spot_close"] - 1.0
    merged["carry_signal"] = (merged["basis"] >= base.entry_basis) & (merged["funding_rate"] >= base.min_funding)
    merged["carry_exit"] = merged["basis"].le(base.exit_basis) | merged["funding_rate"].lt(0)
    valid = merged.dropna(subset=["spot_close", "perp_close", "index_close", "funding_rate"])
    if valid.empty:
        return {"eligible": False, "reason": "no_exact_overlap", "venue": spot_venue}
    if base.require_margin_buffer and not valid["margin_buffer"].notna().any():
        return {"eligible": False, "reason": "margin_buffer_missing", "venue": spot_venue}
    held = False
    entry_basis_value = 0.0
    entry_time: pd.Timestamp | None = None
    returns: list[float] = []
    funding_used: list[float] = []
    entries = 0
    margin_rejections = 0
    periods_held = 0

    def close_position(exit_time: pd.Timestamp, exit_basis: float) -> None:
        nonlocal entry_time, held
        days = max(0.0, (exit_time - entry_time).total_seconds() / 86400.0) if entry_time is not None else 0.0
        borrow = base.annual_borrow_rate * days / 365.0
        collateral = base.annual_collateral_rate * base.collateral_fraction * days / 365.0
        observed = rates.loc[(rates["date"] > entry_time) & (rates["date"] <= exit_time), "funding_rate"]
        funding_income = float(observed.sum())
        funding_used.append(funding_income)
        returns.append(float(entry_basis_value - exit_basis + funding_income - borrow - collateral - base.round_trip_cost))
        held = False
        entry_time = None

    for row in valid.itertuples():
        margin_ok = (
            pd.notna(row.margin_buffer) and float(row.margin_buffer) >= base.min_margin_buffer
            if base.require_margin_buffer
            else pd.isna(row.margin_buffer) or float(row.margin_buffer) >= base.min_margin_buffer
        )
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
                close_position(row.date, float(row.basis))
    if held:
        row = valid.iloc[-1]
        close_position(row["date"], float(row["basis"]))
    profit = float(np.sum(returns))
    stress_deduction = (max(0.0, base.adverse_basis_shock) + max(0.0, base.venue_failure_cost)) if entries else 0.0
    stress_profit = profit - stress_deduction
    return {
        "eligible": True, "venue": spot_venue, "observations": int(len(valid)), "entries": entries,
        "closed_or_force_closed": len(returns), "margin_rejections": margin_rejections,
        "periods_held": periods_held, "basis_mean": float(valid["basis"].mean()),
        "basis_max": float(valid["basis"].max()), "funding_mean": float(valid["funding_rate"].mean()),
        "funding_observations_used": int(sum(1 for value in funding_used if value != 0.0)),
        "funding_income_ratio": float(np.sum(funding_used)), "profit_ratio": profit,
        "profit_pct": profit * 100.0,
        "round_trip_cost": base.round_trip_cost, "stress_profit_ratio": stress_profit,
        "stress_profit_pct": stress_profit * 100.0,
        "stress": {"adverse_basis_shock": base.adverse_basis_shock, "venue_failure_cost": base.venue_failure_cost,
                    "description": "Forced exit after adverse basis shock; funding is not backfilled during failure."},
        "data_coverage": {"margin_buffer": bool(valid["margin_buffer"].notna().any())},
    }


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
    strict_coverage: bool = False,
) -> dict[str, Any]:
    """Evaluate one normalized same-venue cash-and-carry pair."""
    if spot_venue.lower() != perp_venue.lower():
        return {"eligible": False, "reason": "venue_mismatch", "spot_venue": spot_venue, "perp_venue": perp_venue}
    if strict_coverage:
        audit = audit_same_venue_inputs(spot, perp, funding, index, spot_venue)
        if not audit["eligible"]:
            return audit
    base = assumptions or CarryAssumptions(entry_basis, exit_basis, min_funding, round_trip_cost)
    try:
        spot_df, perp_df, funding_df, index_df = _load_inputs(spot, perp, funding, index)
    except FileNotFoundError as exc:
        return {"eligible": False, "reason": "missing_input", "missing": str(exc).split(","), "venue": spot_venue}
    return evaluate_frames(spot_df, perp_df, funding_df, index_df, spot_venue, assumptions=base)


def tune_pair(
    spot: Path,
    perp: Path,
    funding: Path,
    index: Path,
    spot_venue: str,
    perp_venue: str,
    *,
    train_end: str | None = None,
    holdout_start: str | None = None,
    grid: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Select carry thresholds on an early window and report a frozen holdout."""
    if spot_venue.lower() != perp_venue.lower():
        return {"eligible": False, "reason": "venue_mismatch", "spot_venue": spot_venue, "perp_venue": perp_venue}
    try:
        spot_df, perp_df, funding_df, index_df = _load_inputs(spot, perp, funding, index)
    except FileNotFoundError as exc:
        return {"eligible": False, "reason": "missing_input", "missing": str(exc).split(","), "venue": spot_venue}
    start = min(frame["date"].min() for frame in (spot_df, perp_df, funding_df, index_df))
    end = max(frame["date"].max() for frame in (spot_df, perp_df, funding_df, index_df))
    split = pd.Timestamp(train_end, tz="UTC") if train_end else start + (end - start) * 0.6
    holdout = pd.Timestamp(holdout_start, tz="UTC") if holdout_start else split
    grid = grid or [
        {"entry_basis": 0.0025, "exit_basis": 0.0005, "min_funding": 0.0},
        {"entry_basis": 0.0050, "exit_basis": 0.0010, "min_funding": 0.0001},
        {"entry_basis": 0.0075, "exit_basis": 0.0020, "min_funding": 0.0001},
    ]
    def window(frame: pd.DataFrame, start_at: pd.Timestamp | None, end_at: pd.Timestamp | None) -> pd.DataFrame:
        mask = pd.Series(True, index=frame.index)
        if start_at is not None:
            mask &= frame["date"] >= start_at
        if end_at is not None:
            mask &= frame["date"] < end_at
        return frame.loc[mask].copy()
    candidates: list[dict[str, Any]] = []
    for candidate in grid:
        assumptions = CarryAssumptions(**candidate)
        train = evaluate_frames(window(spot_df, None, split), window(perp_df, None, split), window(funding_df, None, split), window(index_df, None, split), spot_venue, assumptions=assumptions)
        score = float(train.get("stress_profit_ratio", -np.inf)) if train.get("eligible") else -np.inf
        candidates.append({"assumptions": assumptions.__dict__, "train": train, "score": score})
    best = max(candidates, key=lambda item: item["score"])
    assumptions = CarryAssumptions(**best["assumptions"])
    frozen = evaluate_frames(window(spot_df, holdout, None), window(perp_df, holdout, None), window(funding_df, holdout, None), window(index_df, holdout, None), spot_venue, assumptions=assumptions)
    return {"eligible": bool(best["train"].get("eligible")), "venue": spot_venue, "train_end": split, "holdout_start": holdout,
            "candidates": candidates, "selected": best["assumptions"], "holdout": frozen,
            "selection_rule": "highest train stress_profit_ratio; no post-holdout retuning"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spot", type=Path, required=True)
    parser.add_argument("--perp", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--spot-venue", required=True)
    parser.add_argument("--perp-venue", required=True)
    parser.add_argument("--strict-coverage", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_pair(
        args.spot,
        args.perp,
        args.funding,
        args.index,
        args.spot_venue,
        args.perp_venue,
        strict_coverage=args.strict_coverage,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
