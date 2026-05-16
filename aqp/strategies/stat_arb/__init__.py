"""Statistical-arbitrage alphas.

Cross-sectional, dollar-neutral strategies trading the residual of a
risk-factor or cluster decomposition. See the research report 2026
appendix for the canonical formulae:

- :class:`MultiClusterMeanReversionAlpha` — cluster-residual mean
  reversion (group stocks into clusters, short overperformers, buy
  underperformers).
- :class:`CrossSectionalResidualAlpha` — Fama-French style
  market/size/value-neutralised residual reversion.

Both alphas are factory-instantiable via the standard
``{class, module_path, kwargs}`` pattern.
"""
from __future__ import annotations

from aqp.strategies.stat_arb.cross_sectional_residual import (
    CrossSectionalResidualAlpha,
)
from aqp.strategies.stat_arb.multi_cluster import (
    MultiClusterMeanReversionAlpha,
)

__all__ = [
    "CrossSectionalResidualAlpha",
    "MultiClusterMeanReversionAlpha",
]
