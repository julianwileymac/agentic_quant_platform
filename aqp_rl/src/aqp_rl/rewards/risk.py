"""Risk-aware reward terms.

- :class:`SharpeTerm` / :class:`SortinoTerm` accumulate per-step returns
  and emit a rolling reward proxy after a warm-up window.
- :class:`DrawdownPenaltyTerm` mirrors FinRL's drawdown component.
- :class:`VolatilityPenaltyTerm` discourages high realised vol.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, ClassVar, Mapping

from aqp_rl.core.reward import RewardTerm


class DrawdownPenaltyTerm(RewardTerm):
    """Penalise the magnitude of the (negative) drawdown.

    Reads ``info["drawdown"]`` (computed by the env step) and returns a
    non-positive contribution scaled by ``weight`` × ``info["drawdown"]``.
    """

    rl_alias: ClassVar[str] = "DrawdownPenaltyTerm"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "risk"

    def __init__(self, *, weight: float = 0.05, threshold: float = 0.0) -> None:
        super().__init__(name="drawdown", weight=weight)
        self.threshold = float(threshold)

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        dd = float(info.get("drawdown", 0.0) or 0.0)
        if dd >= self.threshold:
            return 0.0
        # info["drawdown"] is negative when underwater; we subtract the
        # absolute magnitude (composite multiplies by weight, which is
        # already ``+`` so the *contribution* is negative).
        return float(dd)


class VolatilityPenaltyTerm(RewardTerm):
    """Penalise the rolling stdev of returns observed so far in the episode."""

    rl_alias: ClassVar[str] = "VolatilityPenaltyTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "risk"

    def __init__(self, *, weight: float = 1.0, window: int = 20) -> None:
        super().__init__(name="volatility_penalty", weight=weight)
        self.window = int(window)
        self._returns: deque[float] = deque(maxlen=self.window)

    def reset(self) -> None:
        self._returns.clear()

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        prev = float(state.get("portfolio_value", 0.0) or 0.0)
        curr = float(next_state.get("portfolio_value", prev) or prev)
        if prev > 0:
            self._returns.append((curr - prev) / prev)
        if len(self._returns) < 2:
            return 0.0
        mean = sum(self._returns) / len(self._returns)
        var = sum((r - mean) ** 2 for r in self._returns) / max(len(self._returns) - 1, 1)
        return float(-math.sqrt(var))


class SharpeTerm(RewardTerm):
    """Rolling Sharpe-style reward (``mean(r) / std(r) * sqrt(periods)``).

    Returns 0 until ``min_steps`` returns have accumulated.
    """

    rl_alias: ClassVar[str] = "SharpeTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "risk"

    def __init__(
        self,
        *,
        weight: float = 0.5,
        min_steps: int = 20,
        periods_per_year: int = 252,
    ) -> None:
        super().__init__(name="sharpe", weight=weight)
        self.min_steps = int(min_steps)
        self.periods_per_year = int(periods_per_year)
        self._returns: list[float] = []

    def reset(self) -> None:
        self._returns = []

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        prev = float(state.get("portfolio_value", 0.0) or 0.0)
        curr = float(next_state.get("portfolio_value", prev) or prev)
        if prev > 0:
            self._returns.append((curr - prev) / prev)
        if len(self._returns) < self.min_steps:
            return 0.0
        mean = sum(self._returns) / len(self._returns)
        var = sum((r - mean) ** 2 for r in self._returns) / max(len(self._returns) - 1, 1)
        std = math.sqrt(var)
        if std <= 0:
            return 0.0
        return float(math.sqrt(self.periods_per_year) * mean / std)


class SortinoTerm(RewardTerm):
    """Sortino-style downside-only Sharpe."""

    rl_alias: ClassVar[str] = "SortinoTerm"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "risk"

    def __init__(
        self,
        *,
        weight: float = 0.5,
        min_steps: int = 20,
        periods_per_year: int = 252,
        target_return: float = 0.0,
    ) -> None:
        super().__init__(name="sortino", weight=weight)
        self.min_steps = int(min_steps)
        self.periods_per_year = int(periods_per_year)
        self.target = float(target_return)
        self._returns: list[float] = []

    def reset(self) -> None:
        self._returns = []

    def compute(
        self,
        state: Mapping[str, Any],
        action: Any,
        next_state: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> float:
        prev = float(state.get("portfolio_value", 0.0) or 0.0)
        curr = float(next_state.get("portfolio_value", prev) or prev)
        if prev > 0:
            self._returns.append((curr - prev) / prev)
        if len(self._returns) < self.min_steps:
            return 0.0
        downside = [r - self.target for r in self._returns if r < self.target]
        if not downside:
            return 0.0
        downside_var = sum(d * d for d in downside) / len(downside)
        downside_std = math.sqrt(downside_var)
        if downside_std <= 0:
            return 0.0
        mean_excess = sum(r - self.target for r in self._returns) / len(self._returns)
        return float(math.sqrt(self.periods_per_year) * mean_excess / downside_std)


__all__ = [
    "DrawdownPenaltyTerm",
    "SharpeTerm",
    "SortinoTerm",
    "VolatilityPenaltyTerm",
]
