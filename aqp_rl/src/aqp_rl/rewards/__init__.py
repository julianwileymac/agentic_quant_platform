"""Composable reward terms — drop-in replacements for FinRL's
``default_reward = pnl - turnover_cost - drawdown_penalty``.

Every term is a :class:`aqp_rl.core.reward.RewardTerm` subclass with a
declared ``rl_alias`` so the RL Lab UI can pick it from the palette,
weight it, and preview the resulting reward decomposition over a
sample trajectory.
"""
from __future__ import annotations

from aqp_rl.rewards.constraint import (
    BenchmarkOutperformanceTerm,
    CashIdlePenaltyTerm,
    RiskParityTerm,
)
from aqp_rl.rewards.cost import (
    SlippagePenaltyTerm,
    TransactionCostTerm,
    TurnoverPenaltyTerm,
)
from aqp_rl.rewards.differential_downside import DifferentialDownside
from aqp_rl.rewards.differential_sharpe import DifferentialSharpe
from aqp_rl.rewards.dp_distillation import DPDistillation
from aqp_rl.rewards.exponential_utility import ExponentialUtility
from aqp_rl.rewards.gating import MarginCallTerm, TurbulenceGateTerm
from aqp_rl.rewards.hindsight import HindsightReward
from aqp_rl.rewards.implementation_shortfall import ImplementationShortfall
from aqp_rl.rewards.inventory import RunningInventoryPenalty
from aqp_rl.rewards.inventory_quadratic import InventoryQuadraticPenaltyTerm
from aqp_rl.rewards.pnl import LogReturnTerm, PnLTerm
from aqp_rl.rewards.risk import (
    DrawdownPenaltyTerm,
    SharpeTerm,
    SortinoTerm,
    VolatilityPenaltyTerm,
)
from aqp_rl.rewards.shaping import PotentialBasedShaping
from aqp_rl.rewards.stop_properly import (
    StopProperlyPenaltyTerm,
    StopProperlyWrapper,
)
from aqp_rl.rewards.vol_arb_pnl import VolArbPnLTerm

__all__ = [
    "BenchmarkOutperformanceTerm",
    "CashIdlePenaltyTerm",
    "DPDistillation",
    "DifferentialDownside",
    "DifferentialSharpe",
    "DrawdownPenaltyTerm",
    "ExponentialUtility",
    "HindsightReward",
    "ImplementationShortfall",
    "InventoryQuadraticPenaltyTerm",
    "LogReturnTerm",
    "MarginCallTerm",
    "PnLTerm",
    "PotentialBasedShaping",
    "RiskParityTerm",
    "RunningInventoryPenalty",
    "SharpeTerm",
    "SlippagePenaltyTerm",
    "SortinoTerm",
    "StopProperlyPenaltyTerm",
    "StopProperlyWrapper",
    "TransactionCostTerm",
    "TurbulenceGateTerm",
    "TurnoverPenaltyTerm",
    "VolArbPnLTerm",
    "VolatilityPenaltyTerm",
]
