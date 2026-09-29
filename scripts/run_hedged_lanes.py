#!/usr/bin/env python3
"""Run strict cash-and-carry and two-leg residual research gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.evaluation.cash_carry import audit_same_venue_inputs, evaluate_pair
from research.evaluation.cointegration_book import audit_two_leg_inputs, simulate_pair_from_paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carry-spot", type=Path)
    parser.add_argument("--carry-perp", type=Path)
    parser.add_argument("--carry-funding", type=Path)
    parser.add_argument("--carry-index", type=Path)
    parser.add_argument("--carry-venue")
    parser.add_argument("--residual-asset", type=Path)
    parser.add_argument("--residual-reference", type=Path)
    parser.add_argument("--residual-venue")
    parser.add_argument("--residual-reference-venue")
    parser.add_argument("--min-overlap-days", type=float, default=90.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result: dict[str, Any] = {
        "schema_version": "hedged-research-gates.v1",
        "promotion_rule": "incomplete venue-matched history is not a profitability result",
    }
    carry_paths = (args.carry_spot, args.carry_perp, args.carry_funding, args.carry_index)
    if all(carry_paths) and args.carry_venue:
        spot, perp, funding, index = carry_paths
        result["cash_and_carry"] = {
            "promotion_audit": audit_same_venue_inputs(
                spot,
                perp,
                funding,
                index,
                args.carry_venue,
                min_overlap_days=args.min_overlap_days,
            ),
            "diagnostic": evaluate_pair(spot, perp, funding, index, args.carry_venue, args.carry_venue),
        }
    else:
        result["cash_and_carry"] = {"eligible": False, "reason": "carry_paths_not_supplied"}

    if args.residual_asset and args.residual_reference and args.residual_venue:
        reference_venue = args.residual_reference_venue or args.residual_venue
        audit = audit_two_leg_inputs(
            args.residual_asset,
            args.residual_reference,
            args.residual_venue,
            reference_venue,
            min_overlap_days=args.min_overlap_days,
        )
        lane: dict[str, Any] = {"promotion_audit": audit}
        if audit["eligible"]:
            lane["simulation"] = simulate_pair_from_paths(
                args.residual_asset,
                args.residual_reference,
                asset_venue=args.residual_venue,
                reference_venue=reference_venue,
                strict_contract=True,
            )
        result["two_leg_residual"] = lane
    else:
        result["two_leg_residual"] = {"eligible": False, "reason": "residual_paths_not_supplied"}

    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
