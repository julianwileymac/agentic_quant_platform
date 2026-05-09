"""Observation builder library — composable feature pipelines.

All builders are :class:`aqp.rl.core.observation.BaseObservationBuilder`
subclasses with declared ``rl_alias`` so the RL Lab can drag them onto
the canvas. Compose them via
:class:`aqp.rl.core.observation.StackedObservationBuilder`.
"""
from __future__ import annotations

from aqp.rl.observations.covariance import CovarianceBuilder
from aqp.rl.observations.fundamental import FundamentalBuilder
from aqp.rl.observations.lookback import LookbackStackBuilder
from aqp.rl.observations.microstructure import MicrostructureBuilder
from aqp.rl.observations.portfolio_state import PortfolioStateBuilder
from aqp.rl.observations.technical import TechnicalIndicatorBuilder
from aqp.rl.observations.turbulence import TurbulenceBuilder
from aqp.rl.observations.vix import VIXBuilder

__all__ = [
    "CovarianceBuilder",
    "FundamentalBuilder",
    "LookbackStackBuilder",
    "MicrostructureBuilder",
    "PortfolioStateBuilder",
    "TechnicalIndicatorBuilder",
    "TurbulenceBuilder",
    "VIXBuilder",
]
