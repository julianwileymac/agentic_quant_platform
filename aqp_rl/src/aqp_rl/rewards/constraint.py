"""Constraint / behavioural reward terms.

Inspired by FinRL's ``CashPenaltyEnv`` trick (penalise idle cash) plus
benchmark-outperformance and risk-parity shaping for portfolio research.
"""
from __future__ import annotations

import math
from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import RewardTerm


class CashIdlePenaltyTerm(RewardTerm):
    """Penalise being 100% in cash (FinRL ``CashPenaltyEnv`` trick).

    Detects an idle agent two ways:

    - ``info["shares"] == 0`` (single-asset envs).
    - ``info["weights"]`` all zero (portfolio envs).
    """

    rl_alias: ClassVar[str] = "CashIdlePenaltyTerm"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "behaviour"

    def __init__(self, *, weight: float = 1.0, penalty: float = 0.0005) -> None:
        super().__init__(name="cash_idle_penalty", weight=weight)
        self.penalty = float(penalty)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        shares = info.get("shares")
        if isinstance(shares, (int, float)) and shares == 0:
            return float(-self.penalty)
        weights = info.get("weights") or next_state.get("weights")
        if weights is not None:
            try:
                if all(abs(float(w)) < 1e-9 for w in weights):
                    return float(-self.penalty)
            except Exception:  # noqa: BLE001
                pass
        return 0.0


class BenchmarkOutperformanceTerm(RewardTerm):
    """Reward outperformance vs a fixed benchmark return.

    Uses ``info["benchmark_return"]`` if the env exposes it; otherwise
    treats the benchmark as zero (i.e. rewards positive PnL).
    """

    rl_alias: ClassVar[str] = "BenchmarkOutperformanceTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "behaviour"

    def __init__(self, *, weight: float = 1.0) -> None:
        super().__init__(name="benchmark_outperformance", weight=weight)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        prev = float(state.get("portfolio_value", 0.0) or 0.0)
        curr = float(next_state.get("portfolio_value", prev) or prev)
        port_ret = (curr - prev) / prev if prev > 0 else 0.0
        bench = float(info.get("benchmark_return", 0.0) or 0.0)
        return float(port_ret - bench)


class RiskParityTerm(RewardTerm):
    """Penalise weight concentration (anti-risk-parity = risk concentration)."""

    rl_alias: ClassVar[str] = "RiskParityTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "behaviour"

    def __init__(self, *, weight: float = 1.0) -> None:
        super().__init__(name="risk_parity", weight=weight)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        weights = info.get("weights") or next_state.get("weights")
        if weights is None:
            return 0.0
        try:
            ws = [abs(float(w)) for w in weights]
        except Exception:  # noqa: BLE001
            return 0.0
        if not ws:
            return 0.0
        total = sum(ws)
        if total <= 0:
            return 0.0
        ws_norm = [w / total for w in ws]
        # Higher entropy = more diversified = better.
        entropy = -sum(w * math.log(w + 1e-9) for w in ws_norm)
        return float(entropy / math.log(len(ws_norm) + 1e-9))


__all__ = [
    "BenchmarkOutperformanceTerm",
    "CashIdlePenaltyTerm",
    "RiskParityTerm",
]
