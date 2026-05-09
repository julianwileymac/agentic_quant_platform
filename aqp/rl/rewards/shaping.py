"""Potential-based reward shaping (Ng et al., 1999).

``r' = r + γ·Φ(s') - Φ(s)`` preserves optimal policy ranking. Wraps an
arbitrary potential function (default: scaled portfolio value).
"""
from __future__ import annotations

from typing import Any, Callable, ClassVar, Mapping

from aqp.rl.core.reward import RewardTerm


class PotentialBasedShaping(RewardTerm):
    """Add ``γ·Φ(next_state) - Φ(state)`` as an auxiliary reward."""

    rl_alias: ClassVar[str] = "PotentialBasedShaping"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "shaping"

    def __init__(
        self,
        *,
        weight: float = 1.0,
        gamma: float = 0.99,
        potential: Callable[[Mapping[str, Any]], float] | None = None,
    ) -> None:
        super().__init__(name="potential_shaping", weight=weight)
        self.gamma = float(gamma)
        self.potential = potential or _default_potential

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        phi_s = float(self.potential(state))
        phi_sp = float(self.potential(next_state))
        return float(self.gamma * phi_sp - phi_s)


def _default_potential(state: Mapping[str, Any]) -> float:
    pv = float(state.get("portfolio_value", 0.0) or 0.0)
    initial = float(state.get("initial_balance", 1.0) or 1.0)
    if initial <= 0:
        return 0.0
    return pv / initial - 1.0


__all__ = ["PotentialBasedShaping"]
