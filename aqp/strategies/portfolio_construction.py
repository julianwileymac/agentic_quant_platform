"""Portfolio construction models — target weight rebalancers and classics.

Implements ``IPortfolioConstructionModel`` variants used by extracted
strategies from akquant + analyzingalpha. Includes:

- ``TargetWeightsRebalancer`` — fixed weights per symbol.
- ``MomentumRotation`` — top-K by trailing return.
- ``SixtyForty`` — 60/40 stock/bond rebalance.
- ``BasicRiskParity`` — inverse-vol weighting.
- ``BasicHRP`` — minimal hierarchical risk parity (scipy linkage).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IPortfolioConstructionModel
from aqp.core.registry import register
from aqp.core.types import PortfolioTarget, Signal, Symbol

logger = logging.getLogger(__name__)


def _signal_index(signals: list[Signal]) -> dict[str, Signal]:
    return {s.symbol.vt_symbol: s for s in signals}


@register("TargetWeightsRebalancer", kind="portfolio", tags=("rebalance",))
class TargetWeightsRebalancer(IPortfolioConstructionModel):
    """Allocate fixed target weights to a static set of symbols.

    Weights are read from a ``{vt_symbol: weight}`` mapping. Signals only
    gate which symbols are *active* — the actual weights come from the
    fixed mapping. Unmentioned signals are dropped.
    """

    def __init__(self, target_weights: dict[str, float]) -> None:
        total = sum(abs(w) for w in target_weights.values())
        if total > 1.5:
            logger.warning("Target weights sum to %.2f > 1.5; check leverage", total)
        self.target_weights = dict(target_weights)

    def construct(self, signals: list[Signal], context: dict[str, Any]) -> list[PortfolioTarget]:
        active = _signal_index(signals)
        out: list[PortfolioTarget] = []
        for vt_symbol, weight in self.target_weights.items():
            sym = Symbol.parse(vt_symbol) if vt_symbol not in active else active[vt_symbol].symbol
            out.append(
                PortfolioTarget(
                    symbol=sym,
                    target_weight=float(weight),
                    rationale="fixed_weight",
                )
            )
        return out


@register("MomentumRotationConstruction", kind="portfolio", tags=("momentum", "rotation"))
class MomentumRotationConstruction(IPortfolioConstructionModel):
    """Equal-weight long the top ``top_k`` signals by score.

    Optionally short the bottom ``bottom_k`` for a long-short variant.
    """

    def __init__(self, top_k: int = 5, bottom_k: int = 0, gross: float = 1.0) -> None:
        self.top_k = int(top_k)
        self.bottom_k = int(bottom_k)
        self.gross = float(gross)

    def construct(self, signals: list[Signal], context: dict[str, Any]) -> list[PortfolioTarget]:
        if not signals:
            return []
        ranked = sorted(signals, key=lambda s: s.score or 0.0, reverse=True)
        longs = ranked[: self.top_k]
        shorts = ranked[-self.bottom_k :] if self.bottom_k > 0 else []
        n = len(longs) + len(shorts)
        if n == 0:
            return []
        weight_long = self.gross / max(len(longs), 1) if longs else 0.0
        weight_short = -self.gross / max(len(shorts), 1) if shorts else 0.0
        targets = [
            PortfolioTarget(symbol=s.symbol, target_weight=weight_long, rationale="momentum_top")
            for s in longs
        ]
        targets += [
            PortfolioTarget(symbol=s.symbol, target_weight=weight_short, rationale="momentum_bottom")
            for s in shorts
        ]
        return targets


@register("SixtyForty", kind="portfolio", tags=("rebalance", "classic"))
class SixtyForty(IPortfolioConstructionModel):
    """Classic 60% equity / 40% bond rebalance.

    Symbol IDs default to common ETF proxies but can be overridden.
    """

    def __init__(
        self,
        equity_symbol: str = "SPY.NASDAQ",
        bond_symbol: str = "AGG.NASDAQ",
        equity_weight: float = 0.60,
        bond_weight: float = 0.40,
    ) -> None:
        self.equity_symbol = equity_symbol
        self.bond_symbol = bond_symbol
        self.equity_weight = float(equity_weight)
        self.bond_weight = float(bond_weight)

    def construct(self, signals: list[Signal], context: dict[str, Any]) -> list[PortfolioTarget]:
        return [
            PortfolioTarget(
                symbol=Symbol.parse(self.equity_symbol),
                target_weight=self.equity_weight,
                rationale="60_40_equity",
            ),
            PortfolioTarget(
                symbol=Symbol.parse(self.bond_symbol),
                target_weight=self.bond_weight,
                rationale="60_40_bond",
            ),
        ]


@register("BasicRiskParity", kind="portfolio", tags=("risk_parity",))
class BasicRiskParity(IPortfolioConstructionModel):
    """Inverse-volatility risk parity.

    Reads per-symbol volatility from ``context["volatilities"]`` (a
    ``{vt_symbol: sigma}`` dict). If absent, falls back to equal weights.
    """

    def __init__(self, gross: float = 1.0) -> None:
        self.gross = float(gross)

    def construct(self, signals: list[Signal], context: dict[str, Any]) -> list[PortfolioTarget]:
        if not signals:
            return []
        vols = context.get("volatilities", {})
        weights: dict[str, float] = {}
        for s in signals:
            sigma = float(vols.get(s.symbol.vt_symbol, 1.0))
            weights[s.symbol.vt_symbol] = 1.0 / max(sigma, 1e-6)
        total = sum(weights.values())
        if total <= 0:
            return []
        scale = self.gross / total
        idx = _signal_index(signals)
        return [
            PortfolioTarget(
                symbol=idx[vt].symbol,
                target_weight=w * scale * (1 if (idx[vt].direction or 1) > 0 else -1),
                rationale="risk_parity",
            )
            for vt, w in weights.items()
        ]


@register("BasicHRP", kind="portfolio", tags=("hrp", "hierarchical"))
class BasicHRP(IPortfolioConstructionModel):
    """Hierarchical Risk Parity (Lopez de Prado 2016) — basic single-linkage.

    Requires a returns panel via ``context["returns_panel"]`` (wide
    DataFrame indexed by timestamp with one column per ``vt_symbol``).
    Uses ``scipy.cluster.hierarchy.linkage`` for the dendrogram and
    bisection-based recursive weight allocation.
    """

    def __init__(self, lookback: int = 252, gross: float = 1.0) -> None:
        self.lookback = int(lookback)
        self.gross = float(gross)

    def construct(self, signals: list[Signal], context: dict[str, Any]) -> list[PortfolioTarget]:
        if not signals:
            return []
        try:
            from scipy.cluster.hierarchy import linkage, fcluster  # noqa: F401
            from scipy.spatial.distance import squareform
        except ImportError:
            logger.warning("scipy not available; falling back to equal weights")
            return [
                PortfolioTarget(symbol=s.symbol, target_weight=self.gross / len(signals), rationale="hrp_fallback")
                for s in signals
            ]

        panel: pd.DataFrame | None = context.get("returns_panel")
        if panel is None or panel.empty:
            return [
                PortfolioTarget(symbol=s.symbol, target_weight=self.gross / len(signals), rationale="hrp_no_panel")
                for s in signals
            ]
        cols = [s.symbol.vt_symbol for s in signals if s.symbol.vt_symbol in panel.columns]
        if len(cols) < 2:
            return []
        sub = panel[cols].tail(self.lookback).dropna(how="all").fillna(0.0)
        cov = sub.cov().to_numpy()
        # convert to correlation distance
        corr = sub.corr().to_numpy()
        dist = np.sqrt((1.0 - corr) / 2.0)
        np.fill_diagonal(dist, 0.0)
        condensed = squareform(dist, checks=False)
        link = linkage(condensed, method="single")
        order = self._quasi_diag(link, len(cols))
        weights = self._recursive_bisection(cov, order)

        idx = _signal_index(signals)
        out = []
        for i, w in enumerate(weights):
            vt = cols[order[i]]
            sig = idx[vt]
            direction_sign = 1 if (sig.direction or 1) > 0 else -1
            out.append(
                PortfolioTarget(
                    symbol=sig.symbol,
                    target_weight=float(w * self.gross * direction_sign),
                    rationale="hrp",
                )
            )
        return out

    @staticmethod
    def _quasi_diag(link: np.ndarray, n: int) -> list[int]:
        """Sort items by depth-first traversal of linkage matrix."""
        link = link.astype(int)
        last = link[-1, 0:2].tolist()
        order = list(last)
        cur = n
        while max(order) >= n:
            order_new = []
            for item in order:
                if item < n:
                    order_new.append(item)
                else:
                    pair = link[item - n, 0:2].astype(int).tolist()
                    order_new.extend(pair)
            order = order_new
        return order

    @staticmethod
    def _recursive_bisection(cov: np.ndarray, order: list[int]) -> np.ndarray:
        """Allocate weights via recursive bisection along ``order``."""
        weights = np.ones(len(order))
        items = [order]
        while items:
            new_items: list[list[int]] = []
            for cluster in items:
                if len(cluster) < 2:
                    continue
                mid = len(cluster) // 2
                left = cluster[:mid]
                right = cluster[mid:]
                var_l = BasicHRP._cluster_var(cov, left)
                var_r = BasicHRP._cluster_var(cov, right)
                alpha = 1.0 - var_l / (var_l + var_r) if (var_l + var_r) > 0 else 0.5
                for i_pos, i_glob in enumerate(order):
                    if i_glob in left:
                        weights[i_pos] *= alpha
                    elif i_glob in right:
                        weights[i_pos] *= 1.0 - alpha
                new_items += [left, right]
            items = new_items
        return weights / weights.sum() if weights.sum() > 0 else weights

    @staticmethod
    def _cluster_var(cov: np.ndarray, items: list[int]) -> float:
        sub = cov[np.ix_(items, items)]
        # inverse-variance weights
        ivp = 1.0 / np.diag(sub)
        ivp = ivp / ivp.sum() if ivp.sum() > 0 else ivp
        return float(ivp @ sub @ ivp)


__all__ = [
    "BasicHRP",
    "BasicRiskParity",
    "MomentumRotationConstruction",
    "SixtyForty",
    "TargetWeightsRebalancer",
]
