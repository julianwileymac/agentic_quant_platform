"""Black-Litterman portfolio construction.

Uses ``pypfopt.BlackLittermanModel`` when available; otherwise falls
back to a simple prior-tilted mean-variance allocation. Alpha signals
act as the "views" with confidence derived from signal ``confidence``.
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


@register("BlackLittermanPortfolio")
class BlackLittermanPortfolio(IPortfolioConstructionModel):
    """Blend market-cap prior with alpha-driven views via Black-Litterman."""

    def __init__(
        self,
        max_positions: int = 20,
        long_only: bool = True,
        lookback_bars: int = 252,
        risk_aversion: float = 2.5,
        view_tau: float = 0.05,
    ) -> None:
        self.max_positions = int(max_positions)
        self.long_only = bool(long_only)
        self.lookback_bars = int(lookback_bars)
        self.risk_aversion = float(risk_aversion)
        self.view_tau = float(view_tau)

    def construct(self, signals: list[Signal], context: dict[str, Any]) -> list[PortfolioTarget]:
        if not signals:
            return []
        chosen = sorted(signals, key=lambda s: s.strength * s.confidence, reverse=True)[
            : self.max_positions
        ]
        tickers = [s.symbol.vt_symbol for s in chosen]
        history: pd.DataFrame = context.get("history", pd.DataFrame())
        if history.empty:
            return _equal(chosen)
        pivot = (
            history[history["vt_symbol"].isin(set(tickers))]
            .pivot(index="timestamp", columns="vt_symbol", values="close")
            .sort_index()
            .tail(self.lookback_bars)
            .dropna(how="all")
        )
        if pivot.empty or len(pivot.columns) < 2:
            return _equal(chosen)

        weights = self._optimize(pivot, chosen)
        targets: list[PortfolioTarget] = []
        for vt_symbol, w in weights.items():
            sig = next((s for s in chosen if s.symbol.vt_symbol == vt_symbol), None)
            if sig is None or abs(w) < 1e-4:
                continue
            signed = w * (1.0 if sig.direction == Direction.LONG else -1.0)
            targets.append(
                PortfolioTarget(
                    symbol=sig.symbol,
                    target_weight=float(signed),
                    rationale=f"BL w={w:.3f}",
                    horizon_days=sig.horizon_days,
                )
            )
        return targets

    def _optimize(self, prices: pd.DataFrame, signals: list[Signal]) -> dict[str, float]:
        try:
            from pypfopt import BlackLittermanModel, expected_returns, risk_models

            cov = risk_models.sample_cov(prices)
            # Equal-weighted market prior (no caps available locally).
            n = cov.shape[0]
            pd.Series(np.ones(n) / n, index=cov.columns)
            views = {s.symbol.vt_symbol: 0.01 * (1 if s.direction == Direction.LONG else -1) * s.strength
                     for s in signals if s.symbol.vt_symbol in cov.columns}
            confidences = [s.confidence for s in signals if s.symbol.vt_symbol in cov.columns]
            bl = BlackLittermanModel(
                cov,
                pi=expected_returns.mean_historical_return(prices),
                absolute_views=views,
                view_confidences=confidences or None,
                tau=self.view_tau,
            )
            post_ret = bl.bl_returns()
            post_cov = bl.bl_cov()
            from pypfopt import EfficientFrontier

            ef = EfficientFrontier(
                post_ret, post_cov, weight_bounds=(0 if self.long_only else -1, 1)
            )
            ef.max_sharpe(risk_free_rate=0.0)
            w = ef.clean_weights()
            return {str(k): float(v) for k, v in w.items()}
        except Exception:
            logger.debug("pypfopt Black-Litterman failed; falling back to tilted MVO", exc_info=True)

        returns = prices.pct_change().dropna(how="all")
        mu_hist = returns.mean()
        cov = returns.cov()
        # Tilt historical mean toward each signal.
        tilt = pd.Series(0.0, index=mu_hist.index)
        for s in signals:
            if s.symbol.vt_symbol in tilt.index:
                tilt[s.symbol.vt_symbol] += 0.0001 * s.strength * (
                    1 if s.direction == Direction.LONG else -1
                )
        mu = mu_hist + tilt
        raw = np.linalg.pinv(cov.values) @ mu.values
        if self.long_only:
            raw = np.clip(raw, 0, None)
        total = np.abs(raw).sum()
        raw = np.ones(len(mu)) / len(mu) if total == 0 else raw / total
        return {col: float(raw[i]) for i, col in enumerate(cov.columns)}


def _equal(signals: list[Signal]) -> list[PortfolioTarget]:
    w = 1.0 / len(signals)
    return [
        PortfolioTarget(
            symbol=s.symbol,
            target_weight=w * (1.0 if s.direction == Direction.LONG else -1.0),
            rationale="BL fallback equal",
            horizon_days=s.horizon_days,
        )
        for s in signals
    ]
