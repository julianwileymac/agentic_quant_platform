"""Composable reward terms — drop-in replacements for FinRL's
``default_reward = pnl - turnover_cost - drawdown_penalty``.

Every term is a :class:`aqp.rl.core.reward.RewardTerm` subclass with a
declared ``rl_alias`` so the RL Lab UI can pick it from the palette,
weight it, and preview the resulting reward decomposition over a
sample trajectory.
"""
from __future__ import annotations

from aqp.rl.rewards.constraint import (
    BenchmarkOutperformanceTerm,
    CashIdlePenaltyTerm,
    RiskParityTerm,
)
from aqp.rl.rewards.cost import (
    SlippagePenaltyTerm,
    TransactionCostTerm,
    TurnoverPenaltyTerm,
)
from aqp.rl.rewards.gating import MarginCallTerm, TurbulenceGateTerm
from aqp.rl.rewards.pnl import LogReturnTerm, PnLTerm
from aqp.rl.rewards.risk import (
    DrawdownPenaltyTerm,
    SharpeTerm,
    SortinoTerm,
    VolatilityPenaltyTerm,
)
from aqp.rl.rewards.shaping import PotentialBasedShaping

__all__ = [
    "BenchmarkOutperformanceTerm",
    "CashIdlePenaltyTerm",
    "DrawdownPenaltyTerm",
    "LogReturnTerm",
    "MarginCallTerm",
    "PnLTerm",
    "PotentialBasedShaping",
    "RiskParityTerm",
    "SharpeTerm",
    "SlippagePenaltyTerm",
    "SortinoTerm",
    "TransactionCostTerm",
    "TurbulenceGateTerm",
    "TurnoverPenaltyTerm",
    "VolatilityPenaltyTerm",
]
