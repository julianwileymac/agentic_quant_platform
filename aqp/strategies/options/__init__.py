"""Options strategy library.

These are *traded* options strategies (vs. the P&L math helpers in
:mod:`aqp.options`). Each one emits scheduled `Signal` instances that
describe option legs the order-router opens / closes on a periodic
cadence.

- :class:`VRPDeltaHedgedStraddle` — short ATM straddle harvesting
  the variance-risk premium, delta-hedged with the underlying.
- :class:`IronCondorAlpha` — short iron condor on a single underlying.
- :class:`VarianceSwapSynthetic` — static replication portfolio for a
  variance swap (strip of OTM puts + calls weighted by ``1/K**2``).
"""
from __future__ import annotations

from aqp.strategies.options.iron_condor import IronCondorAlpha
from aqp.strategies.options.variance_swap import VarianceSwapSynthetic
from aqp.strategies.options.vrp_straddle import VRPDeltaHedgedStraddle

__all__ = [
    "IronCondorAlpha",
    "VRPDeltaHedgedStraddle",
    "VarianceSwapSynthetic",
]
