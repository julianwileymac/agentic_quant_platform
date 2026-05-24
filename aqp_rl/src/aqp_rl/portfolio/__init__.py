"""Weight-centric portfolio pipeline (FinRL-X ``f_S -> f_A -> f_T -> f_R``).

The single immutable interface between any RL policy and any downstream
execution mechanism is the target-weight vector ``w_t`` produced by
this pipeline. Composability is total: a researcher can swap any
single module without touching the rest of the pipeline or the
downstream execution semantics.

Stage map
---------

- :class:`StockSelector` (``f_S``) — filter the investable universe by
  liquidity / volatility / momentum criteria.
- :class:`PortfolioAllocator` (``f_A``) — the RL policy. Maps the
  observed state to an unconstrained continuous weight vector.
- :class:`TimingAdjuster` (``f_T``) — scales absolute market exposure
  based on regime detection / turbulence / VIX shocks.
- :class:`RiskOverlay` (``f_R``) — final immutable safety layer.
  Truncates weights that violate hard portfolio constraints
  (max position, max gross, sector neutrality, etc.).
- :class:`WeightCentricPipeline` — composes the four stages into a
  single callable.

This package is the bridge between :mod:`aqp_rl` (the policy stack)
and :mod:`aqp.strategies.portfolio_construction` (the execution
stack). The ``RiskOverlay`` re-uses
:class:`aqp.strategies.portfolio_construction.TargetWeightsRebalancer`
and :class:`aqp.risk.limits.RiskLimits` so the final-stage truncation
math is identical between offline backtests and live broker
execution (deployment-consistent guarantee).
"""
from __future__ import annotations

from aqp_rl.portfolio.allocator import IdentityAllocator, PortfolioAllocator
from aqp_rl.portfolio.pipeline import (
    PipelineState,
    WeightCentricPipeline,
    WeightVector,
)
from aqp_rl.portfolio.risk_overlay import (
    GrossExposureRiskOverlay,
    PositionCapRiskOverlay,
    RiskOverlay,
    StackedRiskOverlay,
)
from aqp_rl.portfolio.selector import (
    LiquiditySelector,
    StaticUniverseSelector,
    StockSelector,
)
from aqp_rl.portfolio.timing import (
    ConstantTimingAdjuster,
    TimingAdjuster,
    TurbulenceTimingAdjuster,
    VolatilityTargetingTimingAdjuster,
)

__all__ = [
    "ConstantTimingAdjuster",
    "GrossExposureRiskOverlay",
    "IdentityAllocator",
    "LiquiditySelector",
    "PipelineState",
    "PortfolioAllocator",
    "PositionCapRiskOverlay",
    "RiskOverlay",
    "StackedRiskOverlay",
    "StaticUniverseSelector",
    "StockSelector",
    "TimingAdjuster",
    "TurbulenceTimingAdjuster",
    "VolatilityTargetingTimingAdjuster",
    "WeightCentricPipeline",
    "WeightVector",
]
