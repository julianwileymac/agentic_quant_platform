"""Semivariance-optimal portfolio (minimise downside deviation)."""
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

STRATEGY_TAGS = ("portfolio", "risk", "semivariance")


@portfolio("EfficientSemivariancePortfolio", tags=STRATEGY_TAGS)
class EfficientSemivariancePortfolio(IPortfolioConstructionModel):
    """Semivariance-optimal allocation (Sortino-style downside aversion)."""

    def __init__(
        self,
        max_positions: int = 15,
        long_only: bool = True,
        lookback_bars: int = 252,
        benchmark: float = 0.0,
        objective: str = "min_semivariance",  # or "efficient_return"
        target_return: float | None = None,
    ) -> None:
        self.max_positions = int(max_positions)
        self.long_only = bool(long_only)
        self.lookback_bars = int(lookback_bars)
        self.benchmark = float(benchmark)
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
            return _equal_weights(chosen, "Semivariance fallback equal")
        weights = self._optimize(returns)
        if not weights:
            weights = _inverse_vol_weights(returns)
        return _targets_from_weights(weights, chosen, rationale_prefix="Semivar")

    def _optimize(self, returns: pd.DataFrame) -> dict[str, float]:
        try:
            from pypfopt import EfficientSemivariance, expected_returns

            mu = expected_returns.mean_historical_return(returns + 1)
            ef = EfficientSemivariance(
                expected_returns=mu,
                returns=returns,
                weight_bounds=(0 if self.long_only else -1, 1),
                benchmark=self.benchmark,
            )
            if self.objective == "efficient_return" and self.target_return is not None:
                ef.efficient_return(target_return=float(self.target_return))
            else:
                ef.min_semivariance()
            raw = ef.clean_weights()
            return {k: float(v) for k, v in raw.items()}
        except Exception:
            logger.debug("pypfopt EfficientSemivariance unavailable/failed", exc_info=True)
            return {}


__all__ = ["EfficientSemivariancePortfolio"]
