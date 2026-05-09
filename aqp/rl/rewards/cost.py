"""Trading-cost reward penalties.

Mirrors FinRL's ``end_total_asset = ... - sell_cost - buy_cost`` baked
into the env, lifted into composable terms so researchers can vary the
cost model without re-implementing the env.
"""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp.rl.core.reward import RewardTerm


class TurnoverPenaltyTerm(RewardTerm):
    """``- cost_pct * turnover`` (turnover = sum of weight changes)."""

    rl_alias: ClassVar[str] = "TurnoverPenaltyTerm"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "cost"

    def __init__(self, *, weight: float = 1.0, cost_pct: float = 0.001) -> None:
        super().__init__(name="turnover_penalty", weight=weight)
        self.cost_pct = float(cost_pct)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        turnover = float(info.get("turnover", 0.0) or 0.0)
        return float(-self.cost_pct * turnover)


class TransactionCostTerm(RewardTerm):
    """Direct ``- info["cost"]`` penalty (env reports per-fill commission)."""

    rl_alias: ClassVar[str] = "TransactionCostTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "cost"

    def __init__(self, *, weight: float = 1.0) -> None:
        super().__init__(name="transaction_cost", weight=weight)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        return float(-(info.get("cost", 0.0) or 0.0))


class SlippagePenaltyTerm(RewardTerm):
    """``- slippage_bps * 1e-4 * notional`` (env reports notional + bps in info)."""

    rl_alias: ClassVar[str] = "SlippagePenaltyTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "cost"

    def __init__(self, *, weight: float = 1.0, slippage_bps: float = 1.0) -> None:
        super().__init__(name="slippage", weight=weight)
        self.slippage_bps = float(slippage_bps)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        notional = float(info.get("notional", info.get("turnover", 0.0)) or 0.0)
        return float(-self.slippage_bps * 1e-4 * notional)


__all__ = [
    "SlippagePenaltyTerm",
    "TransactionCostTerm",
    "TurnoverPenaltyTerm",
]
