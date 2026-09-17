#!/usr/bin/env python3
"""
Lightweight acceptance tests for robustness harness helpers.

Run:
  python tests/acceptance/robustness_acceptance_tests.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "research" / "evaluation"))

from monte_carlo_trades import monte_carlo_from_pnls, sequence_path_stats  # noqa: E402


def test_path_stats_deterministic() -> None:
    # Equity path from 100: 110 -> 105 -> 100, peak 110 -> max DD 10 / 110 = 9.0909%
    stats = sequence_path_stats([10.0, -5.0, -5.0], starting_equity=100.0)
    assert abs(stats["max_dd_pct"] - 9.0909090909) < 1e-6
    assert abs(stats["max_dd_abs"] - 10.0) < 1e-9
    assert int(stats["max_losing_streak"]) == 2


def test_monte_carlo_shape() -> None:
    mc = monte_carlo_from_pnls([10.0, -5.0, 8.0, -4.0], starting_equity=1000.0, permutations=250, seed=1337)
    assert mc["n_trades"] == 4
    assert mc["permutations"] == 250
    assert "p95_max_dd_pct" in mc
    assert mc["p95_max_dd_pct"] >= 0


def run_all() -> None:
    test_path_stats_deterministic()
    test_monte_carlo_shape()
    print("robustness_acceptance_tests: PASS")


if __name__ == "__main__":
    run_all()
