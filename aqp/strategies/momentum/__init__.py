"""Momentum-family strategies.

- :class:`SectorMomentumRotationAlpha` — top-decile sector rotation
  with absolute-trend SMA filter.
- :class:`DualMomentumAlpha` — relative + absolute momentum combined,
  with a safe-haven allocation when the market trend is negative.
- :class:`ResidualMomentumAlpha` — momentum on idiosyncratic returns
  after factor neutralisation.
- :class:`SmoothedMACrossoverAlpha` — low-pass-filtered MA crossover
  signal designed to suppress whipsaws.
"""
from __future__ import annotations

from aqp.strategies.momentum.dual_momentum import DualMomentumAlpha
from aqp.strategies.momentum.residual_momentum import ResidualMomentumAlpha
from aqp.strategies.momentum.sector_rotation import SectorMomentumRotationAlpha
from aqp.strategies.momentum.smoothed_crossover import SmoothedMACrossoverAlpha

__all__ = [
    "DualMomentumAlpha",
    "ResidualMomentumAlpha",
    "SectorMomentumRotationAlpha",
    "SmoothedMACrossoverAlpha",
]
