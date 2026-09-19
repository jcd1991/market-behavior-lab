"""Spot-compatible long-only wrapper for standalone breakout research."""

from StandaloneBreakoutTrend import StandaloneBreakoutTrend


class StandaloneBreakoutTrendSpot(StandaloneBreakoutTrend):
    can_short = False

