"""PRUDEX-Compass — 17-measure × 6-axis evaluation framework.

Port of the PRUDEX-Compass framework (Sun et al. TMLR 2023) into
AQP's :class:`BaseExperiment` contract. The framework decomposes
trading-policy quality into six axes:

| Axis | Code | Measures |
| --- | --- | --- |
| Profitability | P | total_return, annualised_return, cagr |
| Risk-control | R | volatility, max_drawdown, sortino, calmar |
| Universality | U | cross_dataset_sharpe_mean, cross_dataset_sharpe_std |
| Diversification | D | portfolio_weight_entropy, turnover |
| Explainability | E | regime_conditioned_sharpe |
| X-tra evaluation | X | performance_profile_auc, rank_score, extreme_market_score, hit_rate |

Total: 17 named measures across 6 axes. The metrics are computed
from per-step equity / weight history; the 5 companion visualisations
(:mod:`aqp_rl.evaluation.visualizations`) render the per-axis report
as PRIDE-Star, Compass, Performance Profile, Rank Distribution, and
Extreme-Market plots.

This module ships the **metric computation**; the experiment
:class:`PrudexEvaluation` lives at
:mod:`aqp_rl.experiments.prudex_evaluation` so it auto-registers as
an :class:`aqp_rl.core.experiment.BaseExperiment` subclass.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(slots=True)
class PrudexMetrics:
    """One agent's PRUDEX metric bundle (per-axis breakdown)."""

    # Profitability axis (P).
    total_return: float = 0.0
    annualised_return: float = 0.0
    cagr: float = 0.0

    # Risk-control axis (R).
    volatility: float = 0.0
    max_drawdown: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0

    # Universality axis (U).
    cross_dataset_sharpe_mean: float = 0.0
    cross_dataset_sharpe_std: float = 0.0

    # Diversification axis (D).
    portfolio_weight_entropy: float = 0.0
    turnover: float = 0.0

    # Explainability axis (E).
    regime_conditioned_sharpe: float = 0.0

    # X-tra evaluation axis (X).
    performance_profile_auc: float = 0.0
    rank_score: float = 0.0
    extreme_market_score: float = 0.0
    hit_rate: float = 0.0

    # Headline scalar for convenience.
    sharpe_ratio: float = 0.0

    def to_dict(self) -> dict[str, float]:
        from dataclasses import asdict

        return {k: float(v) for k, v in asdict(self).items()}

    def per_axis(self) -> dict[str, dict[str, float]]:
        """Return metrics grouped by PRUDEX axis."""
        return {
            "P": {
                "total_return": self.total_return,
                "annualised_return": self.annualised_return,
                "cagr": self.cagr,
            },
            "R": {
                "volatility": self.volatility,
                "max_drawdown": self.max_drawdown,
                "sortino": self.sortino,
                "calmar": self.calmar,
            },
            "U": {
                "cross_dataset_sharpe_mean": self.cross_dataset_sharpe_mean,
                "cross_dataset_sharpe_std": self.cross_dataset_sharpe_std,
            },
            "D": {
                "portfolio_weight_entropy": self.portfolio_weight_entropy,
                "turnover": self.turnover,
            },
            "E": {"regime_conditioned_sharpe": self.regime_conditioned_sharpe},
            "X": {
                "performance_profile_auc": self.performance_profile_auc,
                "rank_score": self.rank_score,
                "extreme_market_score": self.extreme_market_score,
                "hit_rate": self.hit_rate,
            },
        }


@dataclass(slots=True)
class PrudexReport:
    """Multi-agent PRUDEX report bundle.

    Attributes
    ----------
    per_agent:
        Mapping ``agent_name -> PrudexMetrics``.
    rank_matrix:
        ``(N_agents, M_measures)`` matrix of per-measure ranks.
    metric_names:
        Column labels of ``rank_matrix``.
    extras:
        Free-form payload (e.g. extreme-market windows used).
    """

    per_agent: dict[str, PrudexMetrics]
    rank_matrix: np.ndarray
    metric_names: list[str]
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_agent": {k: v.to_dict() for k, v in self.per_agent.items()},
            "rank_matrix": self.rank_matrix.tolist(),
            "metric_names": list(self.metric_names),
            "extras": dict(self.extras),
        }


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def compute_prudex_metrics(
    *,
    equity_curve: np.ndarray,
    returns: np.ndarray | None = None,
    weights_history: np.ndarray | None = None,
    cross_dataset_sharpes: list[float] | None = None,
    regime_labels: list[int] | None = None,
    periods_per_year: int = 252,
    benchmark_returns: np.ndarray | None = None,
) -> PrudexMetrics:
    """Compute the 17-measure PRUDEX bundle for one agent.

    Parameters
    ----------
    equity_curve:
        ``(T,)`` per-step portfolio value (always non-negative).
    returns:
        Optional pre-computed per-step returns. When ``None``, derived
        from ``equity_curve``.
    weights_history:
        ``(T, N+1)`` per-step weights (cash + N assets). Used by the
        Diversification axis. ``None`` ⇒ entropy = 0, turnover = 0.
    cross_dataset_sharpes:
        Per-dataset Sharpe ratios from a multi-dataset evaluation
        (Universality axis). ``None`` ⇒ mean/std default to 0.
    regime_labels:
        ``(T,)`` per-step regime labels from
        :func:`aqp.analysis.flows.market_dynamics_modeling.slice_and_merge_regime_flow`.
        ``None`` ⇒ regime-conditioned Sharpe defaults to overall Sharpe.
    periods_per_year:
        Annualisation factor for the Sharpe-family measures.
    benchmark_returns:
        Optional benchmark return series for the X-axis
        ``rank_score`` and ``extreme_market_score``.
    """
    eq = np.asarray(equity_curve, dtype=np.float64)
    if eq.size < 2:
        return PrudexMetrics()
    rets = (
        np.asarray(returns, dtype=np.float64)
        if returns is not None
        else np.diff(eq) / np.where(eq[:-1] > 0, eq[:-1], 1e-9)
    )
    out = PrudexMetrics()

    # P axis.
    out.total_return = float((eq[-1] - eq[0]) / max(eq[0], 1e-9))
    n_years = max(len(eq) / periods_per_year, 1.0 / periods_per_year)
    out.annualised_return = float(rets.mean() * periods_per_year)
    out.cagr = float((eq[-1] / max(eq[0], 1e-9)) ** (1.0 / n_years) - 1.0)

    # R axis.
    std = float(rets.std(ddof=1)) if rets.size > 1 else 0.0
    out.volatility = float(std * math.sqrt(periods_per_year))
    out.max_drawdown = _max_drawdown(eq)
    downside = rets[rets < 0]
    downside_std = float(downside.std(ddof=1)) if downside.size > 1 else 0.0
    out.sortino = (
        float(rets.mean() * math.sqrt(periods_per_year) / downside_std)
        if downside_std > 0
        else 0.0
    )
    out.calmar = (
        float(out.annualised_return / abs(out.max_drawdown))
        if abs(out.max_drawdown) > 1e-9
        else 0.0
    )
    out.sharpe_ratio = (
        float(rets.mean() * math.sqrt(periods_per_year) / std) if std > 0 else 0.0
    )

    # U axis.
    if cross_dataset_sharpes:
        xs = np.asarray(cross_dataset_sharpes, dtype=np.float64)
        out.cross_dataset_sharpe_mean = float(xs.mean())
        out.cross_dataset_sharpe_std = float(xs.std(ddof=1)) if xs.size > 1 else 0.0

    # D axis.
    if weights_history is not None:
        w_hist = np.asarray(weights_history, dtype=np.float64)
        if w_hist.ndim == 2 and w_hist.shape[0] > 0:
            # Weight entropy averaged over time (excluding cash).
            entropies = []
            for w in w_hist:
                w_clip = np.clip(w, 1e-9, 1.0)
                w_norm = w_clip / w_clip.sum()
                entropies.append(float(-np.sum(w_norm * np.log(w_norm))))
            out.portfolio_weight_entropy = float(np.mean(entropies))
            if w_hist.shape[0] > 1:
                out.turnover = float(np.mean(np.sum(np.abs(np.diff(w_hist, axis=0)), axis=1)))

    # E axis.
    if regime_labels and len(regime_labels) == len(rets):
        labels = np.asarray(regime_labels, dtype=np.int64)
        per_regime_sharpe: list[float] = []
        for label in np.unique(labels):
            mask = labels == label
            r = rets[mask]
            if r.size > 1 and r.std(ddof=1) > 0:
                per_regime_sharpe.append(
                    float(r.mean() * math.sqrt(periods_per_year) / r.std(ddof=1))
                )
        out.regime_conditioned_sharpe = (
            float(np.mean(per_regime_sharpe)) if per_regime_sharpe else out.sharpe_ratio
        )
    else:
        out.regime_conditioned_sharpe = out.sharpe_ratio

    # X axis.
    out.performance_profile_auc = _performance_profile_auc(rets)
    out.hit_rate = float((rets > 0).mean()) if rets.size > 0 else 0.0
    if benchmark_returns is not None and len(benchmark_returns) == len(rets):
        bench = np.asarray(benchmark_returns, dtype=np.float64)
        # Per-period rank: how often does the agent beat the benchmark?
        out.rank_score = float((rets > bench).mean())
        # Extreme-market score: cumulative return in the worst-decile of
        # benchmark return periods.
        threshold = np.quantile(bench, 0.1)
        extreme_mask = bench <= threshold
        if extreme_mask.any():
            out.extreme_market_score = float(rets[extreme_mask].sum())
    else:
        out.rank_score = float((rets > 0).mean())
        out.extreme_market_score = float(rets[rets < np.quantile(rets, 0.1)].sum()) if rets.size > 10 else 0.0

    return out


def _max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak > 0, peak, 1e-9)
    return float(dd.min())


def _performance_profile_auc(returns: np.ndarray) -> float:
    """Area under the empirical CDF of returns over the [-1, +1] range.

    Mirrors the rliable performance-profile statistic (Agarwal et al.
    NeurIPS 2021). Higher AUC ⇒ more mass at high returns ⇒ better
    profile.
    """
    if returns.size == 0:
        return 0.0
    sorted_r = np.sort(returns)
    cdf = np.arange(1, len(sorted_r) + 1) / len(sorted_r)
    # Trapezoidal integral of (1 - F(r)) from min(r) to max(r).
    return float(np.trapezoid(1 - cdf, sorted_r)) if sorted_r.size > 1 else 0.0


__all__ = [
    "PrudexMetrics",
    "PrudexReport",
    "compute_prudex_metrics",
]
