"""Convert continuous target weights into integer share quantities.

Execution layer helper (not a portfolio construction model). Given a
``{symbol: weight}`` dict + cash + latest prices it returns a
``DiscreteAllocationResult`` with per-symbol integer share counts and the
leftover cash. Supports PyPortfolioOpt's greedy + linear-programming
solvers and a zero-dep fallback for offline environments.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DiscreteAllocationResult:
    shares: dict[str, int] = field(default_factory=dict)
    leftover_cash: float = 0.0
    method: str = "greedy"
    metadata: dict[str, Any] = field(default_factory=dict)


class DiscreteAllocation:
    """Round continuous weights into whole-share positions."""

    def __init__(self, method: str = "greedy") -> None:
        if method not in {"greedy", "lp"}:
            raise ValueError("method must be 'greedy' or 'lp'")
        self.method = method

    def allocate(
        self,
        weights: Mapping[str, float],
        latest_prices: Mapping[str, float],
        total_portfolio_value: float,
        short_ratio: float | None = None,
    ) -> DiscreteAllocationResult:
        weights = {k: float(v) for k, v in weights.items() if abs(v) > 1e-8}
        prices = {k: float(v) for k, v in latest_prices.items() if v and v > 0}
        if not weights or not prices or total_portfolio_value <= 0:
            return DiscreteAllocationResult(method=self.method)
        # Try PyPortfolioOpt first.
        try:
            from pypfopt.discrete_allocation import DiscreteAllocation as _PPFOptDA

            _da = _PPFOptDA(
                weights=weights,
                latest_prices=prices,
                total_portfolio_value=float(total_portfolio_value),
                short_ratio=short_ratio,
            )
            if self.method == "lp":
                shares, leftover = _da.lp_portfolio()
            else:
                shares, leftover = _da.greedy_portfolio()
            return DiscreteAllocationResult(
                shares={k: int(v) for k, v in shares.items()},
                leftover_cash=float(leftover),
                method=self.method,
                metadata={"backend": "pypfopt"},
            )
        except Exception:
            logger.debug("pypfopt DiscreteAllocation unavailable/failed; using fallback", exc_info=True)

        # Fallback: proportional floor() allocation.
        shares: dict[str, int] = {}
        remaining = float(total_portfolio_value)
        for sym, w in weights.items():
            px = prices.get(sym)
            if not px:
                continue
            n = int(np.floor(w * total_portfolio_value / px))
            if n <= 0:
                continue
            shares[sym] = n
            remaining -= n * px
        return DiscreteAllocationResult(
            shares=shares,
            leftover_cash=float(remaining),
            method=self.method,
            metadata={"backend": "fallback"},
        )


__all__ = ["DiscreteAllocation", "DiscreteAllocationResult"]
