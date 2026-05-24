"""``WeightCentricPipeline`` — composes ``f_S -> f_A -> f_T -> f_R``.

Implements the canonical weight-centric protocol contract from
FinRL-X. Each stage takes a :class:`PipelineState` (with the input
weight vector and a context dict) and returns a new state. The
pipeline produces the final target weight vector that the downstream
execution mechanism (backtest engine or live broker) will translate
into orders.

Determinism contract
--------------------

Each stage is a pure function of its inputs — no hidden global
state, no time-dependent randomness without an explicit seed.
Stages may *read* from ``state.context`` (current prices,
turbulence reading, portfolio inventory) but must NOT mutate it.
The pipeline records the per-stage weight vector under
``state.history`` so a downstream LedgerWriter can persist the full
``f_S -> f_A -> f_T -> f_R`` trace for audit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


WeightVector = np.ndarray
"""Numpy 1D array of target portfolio weights, ordered by ``state.universe``."""


@dataclass
class PipelineState:
    """State threaded through every stage of the weight-centric pipeline.

    Attributes
    ----------
    universe:
        Ordered list of ``vt_symbol`` strings the current pipeline
        invocation is allowed to allocate to. Populated by
        :class:`StockSelector` and read by every downstream stage.
    weights:
        Current target weight vector. Same length as :attr:`universe`.
        ``f_A`` writes it, ``f_T`` scales it, ``f_R`` truncates it.
    raw_action:
        Original RL agent action (before any pipeline transformation).
        Preserved so :class:`PortfolioAllocator` subclasses can recover
        the agent's intent for reward attribution.
    context:
        Read-only environment context: ``current_time``, ``prices``,
        ``positions``, ``equity``, ``turbulence``, ``regime`` …
        Stages MUST NOT mutate this dict.
    history:
        Per-stage snapshots of ``weights`` so audit consumers
        (``LedgerWriter``, the RL Lab UI) can reconstruct the
        ``f_S -> f_A -> f_T -> f_R`` trace.
    """

    universe: list[str] = field(default_factory=list)
    weights: WeightVector | None = None
    raw_action: Any | None = None
    context: dict[str, Any] = field(default_factory=dict)
    history: list[tuple[str, WeightVector]] = field(default_factory=list)

    def snapshot(self, stage: str) -> None:
        """Record the current weight vector under ``stage`` for audit.

        Records an empty array when ``weights`` is still ``None``
        (``f_S`` runs before the allocator has assigned weights) so
        the per-stage trace always includes a row for every stage.
        """
        if self.weights is None:
            vec = np.zeros(0, dtype=np.float64)
        else:
            vec = np.asarray(self.weights, dtype=np.float64).copy()
        self.history.append((stage, vec))

    def as_dict(self) -> dict[str, Any]:
        return {
            "universe": list(self.universe),
            "weights": (
                np.asarray(self.weights, dtype=np.float64).tolist()
                if self.weights is not None
                else None
            ),
            "history": [(name, vec.tolist()) for name, vec in self.history],
        }


class WeightCentricPipeline:
    """FinRL-X four-stage weight pipeline composed of pluggable modules.

    Lifecycle inside an RL env's ``step``:

    1. ``f_S`` reads the full universe + per-asset liquidity / vol /
       momentum metrics and outputs the surviving subset.
    2. ``f_A`` (the RL policy) emits raw weights for the surviving
       subset.
    3. ``f_T`` scales the gross exposure based on the current
       turbulence / regime reading.
    4. ``f_R`` enforces hard portfolio constraints (max position,
       max gross, leverage cap, sector neutrality).

    The output of ``f_R`` is the immutable target weight vector that
    flows to the engine via ``context['rl_agent'].last_target_weights``
    and onto the broker via :class:`TargetWeightsRebalancer`.
    """

    def __init__(
        self,
        *,
        selector: Any | None = None,
        allocator: Any | None = None,
        timing: Any | None = None,
        risk_overlay: Any | None = None,
    ) -> None:
        # Lazy imports to break the package-level cycle.
        from aqp_rl.portfolio.allocator import IdentityAllocator
        from aqp_rl.portfolio.risk_overlay import RiskOverlay
        from aqp_rl.portfolio.selector import StaticUniverseSelector
        from aqp_rl.portfolio.timing import ConstantTimingAdjuster

        self.selector = selector or StaticUniverseSelector(universe=[])
        self.allocator = allocator or IdentityAllocator()
        self.timing = timing or ConstantTimingAdjuster(scale=1.0)
        self.risk_overlay = risk_overlay or RiskOverlay()

    # ------------------------------------------------------------------ public

    def __call__(
        self,
        *,
        universe: list[str],
        raw_action: Any,
        context: dict[str, Any],
    ) -> PipelineState:
        return self.run(universe=universe, raw_action=raw_action, context=context)

    def run(
        self,
        *,
        universe: list[str],
        raw_action: Any,
        context: dict[str, Any],
    ) -> PipelineState:
        """Execute the four stages in order and return the final state."""
        state = PipelineState(universe=list(universe), raw_action=raw_action, context=dict(context))

        # f_S — Universe selection.
        state = self.selector.select(state)
        state.snapshot("f_S")

        # f_A — Portfolio allocation. The RL policy lives here.
        state = self.allocator.allocate(state)
        state.snapshot("f_A")

        # f_T — Timing adjustment / macro scaling.
        state = self.timing.adjust(state)
        state.snapshot("f_T")

        # f_R — Hard-constraint risk overlay (last line of defence).
        state = self.risk_overlay.apply(state)
        state.snapshot("f_R")

        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "selector": getattr(self.selector, "to_dict", lambda: {"class": type(self.selector).__name__})(),
            "allocator": getattr(self.allocator, "to_dict", lambda: {"class": type(self.allocator).__name__})(),
            "timing": getattr(self.timing, "to_dict", lambda: {"class": type(self.timing).__name__})(),
            "risk_overlay": getattr(self.risk_overlay, "to_dict", lambda: {"class": type(self.risk_overlay).__name__})(),
        }


__all__ = [
    "PipelineState",
    "WeightCentricPipeline",
    "WeightVector",
]
