"""Quadratic inventory penalty (Cartea-Jaimungal style).

Used by :class:`aqp.rl.envs.OptimalExecutionEnv` and
:class:`aqp.rl.envs.MarketMakingEnv` to bake the running ``-phi * q^2``
penalty into a composable reward term that the lab UI can preview.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp.rl.core.reward import RewardTerm


class InventoryQuadraticPenaltyTerm(RewardTerm):
    """Quadratic inventory penalty ``-phi * q**2``.

    Reads inventory from ``info["inventory"]`` (single-asset envs) or
    falls back to ``next_state["inventory"]``. Returns 0 when neither
    is available so it composes cleanly with other terms.
    """

    rl_alias: ClassVar[str] = "InventoryQuadraticPenaltyTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "constraint"

    def __init__(self, *, weight: float = 1.0, phi: float = 1e-4) -> None:
        super().__init__(name="inventory_quadratic_penalty", weight=weight)
        self.phi = float(phi)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        inv = info.get("inventory")
        if inv is None:
            inv = next_state.get("inventory")
        try:
            q = float(inv)
        except Exception:  # noqa: BLE001
            return 0.0
        return float(-self.phi * q * q)


__all__ = ["InventoryQuadraticPenaltyTerm"]
