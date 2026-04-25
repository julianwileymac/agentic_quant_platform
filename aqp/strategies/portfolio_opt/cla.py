"""Critical Line Algorithm allocation (Markowitz, 1955).

CLA enumerates every corner portfolio along the efficient frontier and
lets the caller pick the max-Sharpe (default) or min-variance point.
Useful when the cvxpy stack isn't available / installable (CLA only
needs numpy + pypfopt).
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.core.interfaces import IPortfolioConstructionModel
from aqp.core.registry import portfolio
from aqp.core.types import PortfolioTarget, Signal
from aqp.strategies.portfolio_opt._base import (
    _equal_weights,
    _inverse_vol_weights,
    _returns_from_history,
    _targets_from_weights,
    _top_signals,
)

logger = logging.getLogger(__name__)

STRATEGY_TAGS = ("portfolio", "frontier", "cla", "markowitz")


@portfolio("CLAPortfolio", tags=STRATEGY_TAGS)
class CLAPortfolio(IPortfolioConstructionModel):
    """Markowitz Critical Line Algorithm."""

    def __init__(
        self,
        max_positions: int = 15,
        long_only: bool = True,
        lookback_bars: int = 252,
        objective: str = "max_sharpe",  # max_sharpe | min_variance | efficient_return
        target_return: float | None = None,
    ) -> None:
        self.max_positions = int(max_positions)
        self.long_only = bool(long_only)
        self.lookback_bars = int(lookback_bars)
        self.objective = objective
        self.target_return = target_return

    def construct(self, signals: list[Signal], context: dict[str, Any]) -> list[PortfolioTarget]:
        if not signals:
            return []
        chosen = _top_signals(signals, self.max_positions)
        tickers = [s.symbol.vt_symbol for s in chosen]
        history: pd.DataFrame = context.get("history", pd.DataFrame())
        returns = _returns_from_history(history, tickers, self.lookback_bars)
        if returns.empty or len(returns.columns) < 2:
            return _equal_weights(chosen, "CLA fallback equal")
        weights = self._optimize(returns)
        if not weights:
            weights = _inverse_vol_weights(returns)
        return _targets_from_weights(weights, chosen, rationale_prefix="CLA")

    def _optimize(self, returns: pd.DataFrame) -> dict[str, float]:
        try:
            from pypfopt import CLA, expected_returns, risk_models

            mu = expected_returns.mean_historical_return(returns + 1)
            sigma = risk_models.sample_cov(returns + 1)
            cla = CLA(mu, sigma, weight_bounds=(0 if self.long_only else -1, 1))
            if self.objective == "min_variance":
                cla.min_volatility()
            elif self.objective == "efficient_return" and self.target_return is not None:
                cla.efficient_return(target_return=float(self.target_return))
            else:
                cla.max_sharpe()
            raw = cla.clean_weights()
            return {k: float(v) for k, v in raw.items()}
        except Exception:
            logger.debug("pypfopt CLA unavailable/failed", exc_info=True)
            return {}


__all__ = ["CLAPortfolio"]
