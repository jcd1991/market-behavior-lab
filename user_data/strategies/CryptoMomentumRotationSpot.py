"""Spot-compatible long-only wrapper for cross-sectional momentum research."""

from CryptoMomentumRotation import CryptoMomentumRotation


class CryptoMomentumRotationSpot(CryptoMomentumRotation):
    can_short = False

