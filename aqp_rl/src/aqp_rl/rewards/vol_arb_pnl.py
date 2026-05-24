"""Lucic-Tse expected vol-arb PnL reward term.

Reads the per-step vol-arb PnL the
:class:`aqp_rl.envs.LucicTsePortfolioEnv` stamps on
``info["vol_arb_pnl_step"]`` and surfaces it as a composable term so
the RL lab can blend it with other penalties (turnover, drawdown).
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import RewardTerm


class VolArbPnLTerm(RewardTerm):
    """Read ``info["vol_arb_pnl_step"]`` as a positive reward signal."""

    rl_alias: ClassVar[str] = "VolArbPnLTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "pnl"

    def __init__(self, *, weight: float = 1.0) -> None:
        super().__init__(name="vol_arb_pnl", weight=weight)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        pnl = info.get("vol_arb_pnl_step")
        if pnl is None:
            pnl = next_state.get("vol_arb_pnl_step", 0.0)
        try:
            return float(pnl)
        except Exception:  # noqa: BLE001
            return 0.0


__all__ = ["VolArbPnLTerm"]
