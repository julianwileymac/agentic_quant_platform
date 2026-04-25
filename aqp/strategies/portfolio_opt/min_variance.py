"""Min-variance + Markowitz mean-variance portfolio construction.

Both classes are :class:`IPortfolioConstructionModel` impls so they
slot into the Lean 5-stage framework alongside ``EqualWeightPortfolio``
and ``SignalWeightedPortfolio``. The covariance matrix is built from
the bars history in ``context["history"]`` over the most recent
``lookback_periods`` rows.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IPortfolioConstructionModel
from aqp.core.registry import register
from aqp.core.types import Direction, PortfolioTarget, Signal

logger = logging.getLogger(__name__)


def _returns_panel(bars: pd.DataFrame, lookback: int) -> pd.DataFrame:
    if bars is None or bars.empty or "close" not in bars.columns:
        return pd.DataFrame()
    pivot = bars.pivot_table(
        index="timestamp", columns="vt_symbol", values="close"
    ).sort_index()
    pivot = pivot.tail(int(lookback)).pct_change().dropna()
    return pivot


def _solve_min_variance(
    returns: pd.DataFrame,
    *,
    long_only: bool,
    max_weight: float,
) -> dict[str, float]:
    if returns.empty or returns.shape[1] < 2:
        return {}
    cov = returns.cov().values
    syms = list(returns.columns)
    try:
        inv = np.linalg.pinv(cov)
        ones = np.ones(len(syms))
        raw = inv @ ones
        denom = ones @ raw
        if denom == 0:
            return {s: 1.0 / len(syms) for s in syms}
        w = raw / denom
    except Exception:
        logger.exception("min_variance: solve failed; using equal weights")
        return {s: 1.0 / len(syms) for s in syms}
    if long_only:
        w = np.clip(w, 0.0, float(max_weight))
        s = w.sum()
        w = w / s if s > 0 else np.ones(len(syms)) / len(syms)
    return {syms[i]: float(w[i]) for i in range(len(syms))}


def _solve_markowitz(
    returns: pd.DataFrame,
    *,
    target_return: float | None,
    risk_aversion: float,
    long_only: bool,
    max_weight: float,
) -> dict[str, float]:
    if returns.empty or returns.shape[1] < 2:
        return {}
    mu = returns.mean().values
    cov = returns.cov().values
    syms = list(returns.columns)
    try:
        from scipy.optimize import minimize

        n = len(syms)
        x0 = np.ones(n) / n
        bounds = [(0.0, float(max_weight)) if long_only else (-float(max_weight), float(max_weight)) for _ in range(n)]
        constraints: list[dict[str, Any]] = [
            {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)},
        ]
        if target_return is not None:
            constraints.append(
                {
                    "type": "eq",
                    "fun": lambda w, mu=mu, t=float(target_return): float(np.dot(w, mu) - t),
                }
            )

        def _obj(w: np.ndarray) -> float:
            variance = float(w @ cov @ w)
            mean = float(w @ mu)
            return float(0.5 * float(risk_aversion) * variance - mean)

        result = minimize(
            _obj,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )
        if not result.success:
            logger.info("markowitz: optimiser failed (%s); using equal weights", result.message)
            return {s: 1.0 / n for s in syms}
        w = np.asarray(result.x, dtype=float)
        if long_only:
            w = np.clip(w, 0.0, float(max_weight))
            sum_w = w.sum()
            w = w / sum_w if sum_w > 0 else np.ones(n) / n
        return {syms[i]: float(w[i]) for i in range(n)}
    except Exception:
        logger.exception("markowitz: solve failed; falling back to min-variance")
        return _solve_min_variance(returns, long_only=long_only, max_weight=max_weight)


def _signals_to_universe(signals: list[Signal]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in signals:
        vt = s.symbol.vt_symbol
        if vt in seen:
            continue
        seen.add(vt)
        out.append(vt)
    return out


@register("MinVariancePortfolio", kind="portfolio", tags=("portfolio", "optimizer", "min_variance"))
class MinVariancePortfolio(IPortfolioConstructionModel):
    """Closed-form min-variance over the signal universe.

    Pulls bars history from ``context["history"]`` (the engine
    populates this for every stage 3 invocation).
    """

    def __init__(
        self,
        lookback_periods: int = 252,
        max_weight: float = 1.0,
        long_only: bool = True,
        max_positions: int | None = None,
    ) -> None:
        self.lookback_periods = int(lookback_periods)
        self.max_weight = float(max_weight)
        self.long_only = bool(long_only)
        self.max_positions = int(max_positions) if max_positions else None

    def construct(
        self,
        signals: list[Signal],
        context: dict[str, Any],
    ) -> list[PortfolioTarget]:
        if not signals:
            return []
        ranked = sorted(signals, key=lambda s: s.strength * s.confidence, reverse=True)
        if self.long_only:
            ranked = [s for s in ranked if s.direction == Direction.LONG]
        if self.max_positions:
            ranked = ranked[: self.max_positions]
        if not ranked:
            return []
        universe = _signals_to_universe(ranked)
        bars: pd.DataFrame = context.get("history", pd.DataFrame())
        bars = bars[bars["vt_symbol"].isin(universe)] if not bars.empty else bars
        returns = _returns_panel(bars, self.lookback_periods)
        if returns.empty:
            n = len(universe)
            weights = {s: 1.0 / n for s in universe}
        else:
            weights = _solve_min_variance(returns, long_only=self.long_only, max_weight=self.max_weight)
            for s in universe:
                weights.setdefault(s, 0.0)
        out: list[PortfolioTarget] = []
        for s in ranked:
            w = float(weights.get(s.symbol.vt_symbol, 0.0))
            if w <= 0:
                continue
            sign = 1.0 if s.direction == Direction.LONG else -1.0
            out.append(
                PortfolioTarget(
                    symbol=s.symbol,
                    target_weight=sign * w,
                    rationale=f"min_variance | {s.rationale or ''}",
                    horizon_days=s.horizon_days,
                )
            )
        return out


@register(
    "MarkowitzPortfolio",
    kind="portfolio",
    tags=("portfolio", "optimizer", "markowitz", "mean_variance"),
)
class MarkowitzPortfolio(IPortfolioConstructionModel):
    """Mean-variance with optional target-return constraint.

    Maximises ``mu.T @ w - 0.5 * risk_aversion * w.T @ cov @ w``
    subject to weights summing to 1 and bounds
    ``[0, max_weight]`` (long-only) or ``[-max_weight, max_weight]``.
    """

    def __init__(
        self,
        lookback_periods: int = 252,
        risk_aversion: float = 1.0,
        target_return: float | None = None,
        max_weight: float = 1.0,
        long_only: bool = True,
        max_positions: int | None = None,
    ) -> None:
        self.lookback_periods = int(lookback_periods)
        self.risk_aversion = float(risk_aversion)
        self.target_return = float(target_return) if target_return is not None else None
        self.max_weight = float(max_weight)
        self.long_only = bool(long_only)
        self.max_positions = int(max_positions) if max_positions else None

    def construct(
        self,
        signals: list[Signal],
        context: dict[str, Any],
    ) -> list[PortfolioTarget]:
        if not signals:
            return []
        ranked = sorted(signals, key=lambda s: s.strength * s.confidence, reverse=True)
        if self.long_only:
            ranked = [s for s in ranked if s.direction == Direction.LONG]
        if self.max_positions:
            ranked = ranked[: self.max_positions]
        if not ranked:
            return []
        universe = _signals_to_universe(ranked)
        bars: pd.DataFrame = context.get("history", pd.DataFrame())
        bars = bars[bars["vt_symbol"].isin(universe)] if not bars.empty else bars
        returns = _returns_panel(bars, self.lookback_periods)
        weights = _solve_markowitz(
            returns,
            target_return=self.target_return,
            risk_aversion=self.risk_aversion,
            long_only=self.long_only,
            max_weight=self.max_weight,
        )
        if not weights:
            n = len(universe)
            weights = {s: 1.0 / n for s in universe}
        out: list[PortfolioTarget] = []
        for s in ranked:
            w = float(weights.get(s.symbol.vt_symbol, 0.0))
            if w <= 0:
                continue
            sign = 1.0 if s.direction == Direction.LONG else -1.0
            out.append(
                PortfolioTarget(
                    symbol=s.symbol,
                    target_weight=sign * w,
                    rationale=f"markowitz | {s.rationale or ''}",
                    horizon_days=s.horizon_days,
                )
            )
        return out


__all__ = ["MarkowitzPortfolio", "MinVariancePortfolio"]
