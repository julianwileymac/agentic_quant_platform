"""Hierarchical Risk Parity (ML4T Chapter 13 port).

Implements the four-step HRP allocation:

1. Compute a correlation distance matrix.
2. Hierarchically cluster symbols (single-linkage by default).
3. Quasi-diagonalise the covariance matrix.
4. Recursively split inverse-variance allocations.

Pure numpy/scipy; falls back to inverse-volatility weights if scipy is
absent (the clustering step would fail without it).
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


@register("HierarchicalRiskParity")
class HierarchicalRiskParity(IPortfolioConstructionModel):
    """HRP allocation (de Prado, *Advances in Financial ML*, ch. 16)."""

    def __init__(
        self,
        max_positions: int = 20,
        long_only: bool = True,
        lookback_bars: int = 252,
        linkage_method: str = "single",
    ) -> None:
        self.max_positions = int(max_positions)
        self.long_only = bool(long_only)
        self.lookback_bars = int(lookback_bars)
        self.linkage_method = linkage_method

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
            .pct_change()
            .dropna(how="all")
        )
        if pivot.empty or len(pivot.columns) < 2:
            return _equal(chosen)
        weights = self._hrp(pivot)
        sign = {s.symbol.vt_symbol: 1.0 if s.direction == Direction.LONG else -1.0 for s in chosen}
        targets: list[PortfolioTarget] = []
        for vt_symbol, w in weights.items():
            if vt_symbol not in sign:
                continue
            signed = w * sign[vt_symbol]
            if abs(signed) < 1e-4:
                continue
            signal = next(s for s in chosen if s.symbol.vt_symbol == vt_symbol)
            targets.append(
                PortfolioTarget(
                    symbol=signal.symbol,
                    target_weight=float(signed),
                    rationale=f"HRP w={w:.3f}",
                    horizon_days=signal.horizon_days,
                )
            )
        return targets

    # ------------------------------------------------------------------
    # Core HRP math
    # ------------------------------------------------------------------

    def _hrp(self, returns: pd.DataFrame) -> dict[str, float]:
        try:
            from scipy.cluster.hierarchy import linkage
        except Exception:
            logger.warning("scipy missing; HRP falling back to inverse-volatility")
            return self._inverse_vol(returns)

        corr = returns.corr()
        cov = returns.cov()
        dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
        try:
            Z = linkage(dist.values, method=self.linkage_method)
        except Exception:
            logger.exception("scipy linkage failed; falling back to inverse-vol")
            return self._inverse_vol(returns)
        sort_ix = self._quasi_diagonal(Z)
        ordered = corr.columns[sort_ix].tolist()
        weights = self._recursive_bisection(cov.loc[ordered, ordered])
        return weights.to_dict()

    @staticmethod
    def _quasi_diagonal(link: np.ndarray) -> list[int]:
        link = link.astype(int)
        sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
        num_items = link[-1, 3]
        while sort_ix.max() >= num_items:
            sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
            df = sort_ix[sort_ix >= num_items]
            i = df.index
            j = df.values - num_items
            sort_ix[i] = link[j, 0]
            df = pd.Series(link[j, 1], index=i + 1)
            sort_ix = pd.concat([sort_ix, df]).sort_index()
            sort_ix.index = range(sort_ix.shape[0])
        return sort_ix.tolist()

    def _recursive_bisection(self, cov: pd.DataFrame) -> pd.Series:
        weights = pd.Series(1.0, index=cov.columns)
        clusters = [list(range(cov.shape[0]))]
        while clusters:
            clusters = [
                c[start:stop]
                for c in clusters
                for start, stop in ((0, len(c) // 2), (len(c) // 2, len(c)))
                if len(c) > 1
            ]
            for i in range(0, len(clusters), 2):
                c0 = clusters[i]
                c1 = clusters[i + 1] if i + 1 < len(clusters) else []
                if not c1:
                    continue
                var0 = self._cluster_var(cov, c0)
                var1 = self._cluster_var(cov, c1)
                alpha = 1 - var0 / (var0 + var1)
                weights.iloc[c0] *= alpha
                weights.iloc[c1] *= 1 - alpha
        return weights / weights.sum()

    @staticmethod
    def _cluster_var(cov: pd.DataFrame, indices: list[int]) -> float:
        sub = cov.iloc[indices, indices]
        ivp = 1.0 / np.diag(sub.values)
        ivp /= ivp.sum()
        return float(ivp @ sub.values @ ivp)

    @staticmethod
    def _inverse_vol(returns: pd.DataFrame) -> dict[str, float]:
        vols = returns.std()
        inv = 1.0 / vols.replace(0, np.nan)
        inv = inv.dropna()
        if inv.empty:
            return {}
        weights = inv / inv.sum()
        return weights.to_dict()


def _equal(signals: list[Signal]) -> list[PortfolioTarget]:
    w = 1.0 / len(signals)
    return [
        PortfolioTarget(
            symbol=s.symbol,
            target_weight=w * (1.0 if s.direction == Direction.LONG else -1.0),
            rationale="HRP fallback equal",
            horizon_days=s.horizon_days,
        )
        for s in signals
    ]
