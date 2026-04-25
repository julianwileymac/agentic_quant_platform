"""Mean-variance portfolio construction (Markowitz)."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IPortfolioConstructionModel
from aqp.core.registry import register
from aqp.core.types import Direction, PortfolioTarget, Signal

logger = logging.getLogger(__name__)


@register("MeanVariancePortfolio")
class MeanVariancePortfolio(IPortfolioConstructionModel):
    """Mean-variance optimal weights over the signalled subset.

    Tries ``pypfopt`` if installed; falls back to numpy-based closed-form
    (``w = Σ⁻¹ μ``, normalised). Long-only by default.
    """

    def __init__(
        self,
        max_positions: int = 10,
        long_only: bool = True,
        cov_method: str = "sample",
        lookback_bars: int = 252,
    ) -> None:
        self.max_positions = int(max_positions)
        self.long_only = bool(long_only)
        self.cov_method = cov_method
        self.lookback_bars = int(lookback_bars)

    def construct(self, signals: list[Signal], context: dict[str, Any]) -> list[PortfolioTarget]:
        if not signals:
            return []
        chosen = sorted(signals, key=lambda s: s.strength * s.confidence, reverse=True)[
            : self.max_positions
        ]
        tickers = [s.symbol.vt_symbol for s in chosen]
        history: pd.DataFrame = context.get("history", pd.DataFrame())
        if history.empty:
            return _equal_weights(chosen)
        pivot = (
            history[history["vt_symbol"].isin(set(tickers))]
            .pivot(index="timestamp", columns="vt_symbol", values="close")
            .sort_index()
            .tail(self.lookback_bars)
            .pct_change()
            .dropna(how="all")
        )
        if pivot.empty or len(pivot.columns) < 2:
            return _equal_weights(chosen)
        weights = self._optimize(pivot)
        sign = {s.symbol.vt_symbol: 1.0 if s.direction == Direction.LONG else -1.0 for s in chosen}
        targets: list[PortfolioTarget] = []
        for vt_symbol, w in weights.items():
            if vt_symbol not in sign:
                continue
            signed = w * sign[vt_symbol]
            if abs(signed) < 1e-4:
                continue
            # Look up the signal so we can preserve horizon/rationale
            signal = next(s for s in chosen if s.symbol.vt_symbol == vt_symbol)
            targets.append(
                PortfolioTarget(
                    symbol=signal.symbol,
                    target_weight=float(signed),
                    rationale=f"MVO w={w:.3f}",
                    horizon_days=signal.horizon_days,
                )
            )
        return targets

    def _optimize(self, returns: pd.DataFrame) -> dict[str, float]:
        try:
            from pypfopt import EfficientFrontier, expected_returns, risk_models

            mu = expected_returns.mean_historical_return(returns + 1).values  # mean_hist_ret expects prices
            sigma = risk_models.sample_cov(returns + 1).values
            ef = EfficientFrontier(mu, sigma, weight_bounds=(0 if self.long_only else -1, 1))
            ef.max_sharpe()
            weights = ef.clean_weights()
            return {col: float(weights.get(i, 0)) for i, col in enumerate(returns.columns)}
        except Exception:
            logger.debug("pypfopt unavailable or failed; falling back to numpy MVO", exc_info=True)

        # numpy fallback: w = Σ⁻¹ μ, normalised.
        mu = returns.mean().values
        sigma = returns.cov().values
        try:
            raw = np.linalg.pinv(sigma) @ mu
        except Exception:
            raw = np.ones(len(mu)) / len(mu)
        if self.long_only:
            raw = np.clip(raw, 0, None)
        total = np.abs(raw).sum()
        raw = np.ones(len(mu)) / len(mu) if total == 0 else raw / total
        return {col: float(raw[i]) for i, col in enumerate(returns.columns)}


def _equal_weights(signals: list[Signal]) -> list[PortfolioTarget]:
    if not signals:
        return []
    w = 1.0 / len(signals)
    return [
        PortfolioTarget(
            symbol=s.symbol,
            target_weight=w * (1.0 if s.direction == Direction.LONG else -1.0),
            rationale="MVO fallback equal weight",
            horizon_days=s.horizon_days,
        )
        for s in signals
    ]
