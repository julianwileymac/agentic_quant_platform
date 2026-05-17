"""``f_A`` — portfolio allocation stage (the RL policy).

In the canonical FinRL-X flow ``f_A`` is the place where the trained
RL agent's action vector becomes a (still unconstrained) target weight
vector. The default :class:`IdentityAllocator` treats the raw action
as the weight vector directly; specialised subclasses may apply
softmax / sigmoid / target-position transforms to map continuous
actions onto a constrained simplex.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from aqp.rl.portfolio.pipeline import PipelineState


class PortfolioAllocator:
    """Base class for the ``f_A`` stage.

    Subclasses override :meth:`allocate` to populate
    ``state.weights`` from ``state.raw_action``.
    """

    def allocate(self, state: PipelineState) -> PipelineState:
        return state

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__}


class IdentityAllocator(PortfolioAllocator):
    """Treat the raw RL action as the unconstrained weight vector.

    Used when the policy already emits valid simplex / target-percent
    weights (e.g. with :class:`SoftmaxWeightsAction` action space).
    """

    def allocate(self, state: PipelineState) -> PipelineState:
        action = state.raw_action
        if action is None:
            state.weights = np.zeros(len(state.universe), dtype=np.float64)
            return state
        arr = np.asarray(action, dtype=np.float64).ravel()
        if len(arr) != len(state.universe):
            # The action is shorter than the universe (e.g. a stock
            # selector dropped names). Pad with zeros so length
            # invariants hold; truncate if longer.
            if len(arr) > len(state.universe):
                arr = arr[: len(state.universe)]
            else:
                padded = np.zeros(len(state.universe), dtype=np.float64)
                padded[: len(arr)] = arr
                arr = padded
        state.weights = arr
        return state


class SoftmaxAllocator(PortfolioAllocator):
    """Softmax the raw action vector for long-only simplex allocation."""

    def __init__(self, *, temperature: float = 1.0) -> None:
        self.temperature = float(temperature)

    def allocate(self, state: PipelineState) -> PipelineState:
        action = state.raw_action
        if action is None:
            state.weights = np.zeros(len(state.universe), dtype=np.float64)
            return state
        arr = np.asarray(action, dtype=np.float64).ravel()
        if len(arr) > len(state.universe):
            arr = arr[: len(state.universe)]
        elif len(arr) < len(state.universe):
            padded = np.full(len(state.universe), -1e9, dtype=np.float64)
            padded[: len(arr)] = arr
            arr = padded
        scaled = arr / max(self.temperature, 1e-6)
        scaled = scaled - scaled.max()
        exp = np.exp(scaled)
        denom = exp.sum()
        state.weights = exp / denom if denom > 0 else np.zeros_like(exp)
        return state

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__, "temperature": self.temperature}


__all__ = [
    "IdentityAllocator",
    "PortfolioAllocator",
    "SoftmaxAllocator",
]
