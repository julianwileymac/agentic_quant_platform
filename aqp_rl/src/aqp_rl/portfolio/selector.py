"""``f_S`` — investable-universe selection stage.

A :class:`StockSelector` filters the configured universe down to the
subset that meets per-bar liquidity / volatility / momentum criteria.
Concrete subclasses:

- :class:`StaticUniverseSelector` — fixed universe; pass-through.
- :class:`LiquiditySelector` — drop names whose recent average daily
  volume falls below a configurable floor. Default used by the
  FinRL-X blueprint examples.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from aqp_rl.portfolio.pipeline import PipelineState

logger = logging.getLogger(__name__)


class StockSelector:
    """Base class for the ``f_S`` stage.

    Subclasses override :meth:`select` to mutate ``state.universe``
    (and resize ``state.weights`` if already populated by a previous
    pipeline step — for the canonical ``f_S -> f_A -> ...`` order the
    weight vector is still ``None`` at this point).
    """

    def select(self, state: PipelineState) -> PipelineState:
        return state

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__}


class StaticUniverseSelector(StockSelector):
    """Passes the configured universe through unchanged.

    Useful when the RL spec already enumerates the universe via
    :attr:`RLExperimentSpec.universe.symbols` and the env does not
    want to re-filter on top of it.
    """

    def __init__(self, *, universe: list[str] | None = None) -> None:
        self.universe = list(universe or [])

    def select(self, state: PipelineState) -> PipelineState:
        if self.universe and not state.universe:
            state.universe = list(self.universe)
        return state

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__, "universe": list(self.universe)}


class LiquiditySelector(StockSelector):
    """Drop names with rolling average dollar volume below ``min_dollar_volume``.

    Reads ``context['liquidity']`` — a ``{vt_symbol: rolling_adv}``
    map populated by the env. Falls back to the configured universe
    if no liquidity table is available (e.g. synthetic envs).
    """

    def __init__(self, *, min_dollar_volume: float = 1_000_000.0) -> None:
        self.min_dollar_volume = float(min_dollar_volume)

    def select(self, state: PipelineState) -> PipelineState:
        liquidity: dict[str, float] | None = state.context.get("liquidity")
        if not liquidity:
            return state
        survivors = [
            sym
            for sym in state.universe
            if float(liquidity.get(sym, 0.0)) >= self.min_dollar_volume
        ]
        if survivors:
            state.universe = survivors
            if state.weights is not None and len(state.weights) != len(survivors):
                # If the allocator already produced a vector we resize
                # by mask. This branch is unusual (selector runs first
                # in the canonical flow) but kept defensive.
                state.weights = np.asarray(state.weights[: len(survivors)], dtype=np.float64)
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "min_dollar_volume": self.min_dollar_volume,
        }


__all__ = [
    "LiquiditySelector",
    "StaticUniverseSelector",
    "StockSelector",
]
