"""Observation builder library — composable feature pipelines.

All builders are :class:`aqp_rl.core.observation.BaseObservationBuilder`
subclasses with declared ``rl_alias`` so the RL Lab can drag them onto
the canvas. Compose them via
:class:`aqp_rl.core.observation.StackedObservationBuilder`.
"""
from __future__ import annotations

from aqp_rl.observations.covariance import CovarianceBuilder
from aqp_rl.observations.fundamental import FundamentalBuilder
from aqp_rl.observations.lookback import LookbackStackBuilder
from aqp_rl.observations.microstructure import MicrostructureBuilder
from aqp_rl.observations.portfolio_state import PortfolioStateBuilder
from aqp_rl.observations.regime import RegimeAwareObservation
from aqp_rl.observations.technical import TechnicalIndicatorBuilder
from aqp_rl.observations.turbulence import TurbulenceBuilder
from aqp_rl.observations.vix import VIXBuilder

__all__ = [
    "CovarianceBuilder",
    "FundamentalBuilder",
    "LookbackStackBuilder",
    "MicrostructureBuilder",
    "PortfolioStateBuilder",
    "RegimeAwareObservation",
    "TechnicalIndicatorBuilder",
    "TurbulenceBuilder",
    "VIXBuilder",
]
