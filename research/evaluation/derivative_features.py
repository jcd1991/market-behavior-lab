"""Pure, venue-neutral derivative feature calculations.

These helpers deliberately return NaN when a source is absent.  They are for
research diagnostics and strategy lanes, not for manufacturing historical
funding or open-interest values.
"""

from __future__ import annotations

import pandas as pd


def add_basis_oi_features(
    candles: pd.DataFrame,
    *,
    mark: pd.DataFrame | None = None,
    index: pd.DataFrame | None = None,
    open_interest: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add backward-looking basis/OI interaction columns to OHLCV candles."""
    out = candles.copy()
    out["date"] = pd.to_datetime(out.get("date"), utc=True, errors="coerce")
    out = out.sort_values("date")
    close = pd.to_numeric(out.get("close"), errors="coerce")

    def merge_value(source: pd.DataFrame | None, name: str, candidates: tuple[str, ...]) -> pd.Series:
        result = pd.Series(float("nan"), index=out.index, dtype=float)
        if source is None or source.empty or "date" not in source:
            return result
        src = source.copy()
        src["date"] = pd.to_datetime(src["date"], utc=True, errors="coerce")
        for col in candidates:
            if col in src:
                src[name] = pd.to_numeric(src[col], errors="coerce")
                break
        else:
            return result
        src = src[["date", name]].dropna(subset=["date"]).sort_values("date")
        left = out[["date"]].copy()
        merged = pd.merge_asof(left, src, on="date", direction="backward")
        return pd.to_numeric(merged[name], errors="coerce").set_axis(out.index)

    mark_close = merge_value(mark, "mark_close", ("close", "mark_price", "mark"))
    index_close = merge_value(index, "index_close", ("close", "index_price", "index"))
    oi_value = merge_value(
        open_interest,
        "open_interest",
        ("open_interest_amount", "open_interest_value", "open_interest", "oi"),
    )
    out["mark_close"] = mark_close
    out["index_close"] = index_close
    out["basis"] = ((mark_close - index_close) / index_close.replace(0, pd.NA)).astype(float)
    out["oi_change_pct"] = oi_value.pct_change()
    price_change = close.pct_change()
    out["basis_oi_trend_long"] = (price_change > 0) & (out["oi_change_pct"] > 0)
    out["basis_oi_trend_short"] = (price_change < 0) & (out["oi_change_pct"] > 0)
    out["basis_oi_capitulation"] = (price_change < 0) & (out["oi_change_pct"] < 0)
    out["derivative_features_available"] = mark_close.notna() | index_close.notna() | oi_value.notna()
    return out


def funding_policy(funding: pd.Series, *, side: str, max_abs: float = 0.01) -> pd.Series:
    """Return a conservative funding filter: long prefers non-positive carry."""
    values = pd.to_numeric(funding, errors="coerce")
    valid = values.notna() & values.abs().le(float(max_abs))
    if side.lower() == "short":
        return valid & (values >= 0)
    return valid & (values <= 0)
