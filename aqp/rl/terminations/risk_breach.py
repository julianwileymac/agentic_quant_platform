"""Risk-breach termination.

Triggers when the absolute inventory or absolute vega exposure exceeds
configured caps. Used by :class:`aqp.rl.envs.MarketMakingEnv` and
:class:`aqp.rl.envs.LucicTsePortfolioEnv` so PPO/SAC training rolls
out short, intentionally-risky episodes when the agent's policy lets
inventory blow up.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp.rl.core.termination import BaseTerminationCondition


class RiskBreachTermination(BaseTerminationCondition):
    """End the episode when inventory or vega exposure breach caps."""

    rl_alias: ClassVar[str] = "RiskBreachTermination"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "risk"

    def __init__(
        self,
        *,
        inventory_cap: float = 100.0,
        vega_cap: float = 1000.0,
    ) -> None:
        super().__init__(name="risk_breach_termination")
        self.inventory_cap = float(inventory_cap)
        self.vega_cap = float(vega_cap)

    def check(self, idx: int, horizon: int, env_state: Mapping[str, Any]) -> bool:
        inv = env_state.get("inventory")
        if inv is not None:
            try:
                if abs(float(inv)) >= self.inventory_cap:
                    return True
            except Exception:  # noqa: BLE001
                pass
        max_inv = env_state.get("max_inventory")
        if max_inv is not None:
            try:
                if abs(float(max_inv)) >= self.inventory_cap:
                    return True
            except Exception:  # noqa: BLE001
                pass
        vega = env_state.get("vega")
        if vega is not None:
            try:
                if abs(float(vega)) >= self.vega_cap:
                    return True
            except Exception:  # noqa: BLE001
                pass
        return False


__all__ = ["RiskBreachTermination"]
