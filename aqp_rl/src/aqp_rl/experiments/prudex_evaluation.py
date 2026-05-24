"""``PrudexEvaluation`` — aggregate PRUDEX-Compass over multiple agents.

Runs each agent's per-step equity curve through
:func:`compute_prudex_metrics`, then ranks agents per metric and
emits a :class:`PrudexReport` ready for the 5 visualisation helpers.

Hard rule 19: auto-registers via the :class:`RLComponent` metaclass.
Hard rule 18: results land in ``rl_runs.result_summary`` via the
parent :class:`RLRuntime`; no direct Iceberg writes from this
experiment.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

import numpy as np

from aqp_rl.core.experiment import BaseExperiment
from aqp_rl.evaluation.prudex_compass import (
    PrudexMetrics,
    PrudexReport,
    compute_prudex_metrics,
)

logger = logging.getLogger(__name__)


class PrudexEvaluation(BaseExperiment):
    """Compute the PRUDEX-Compass report across N agents on M datasets.

    Parameters
    ----------
    periods_per_year:
        Annualisation factor. ``252`` for daily, ``31_536_000`` for
        per-second HFT, etc.
    """

    rl_alias: ClassVar[str] = "prudex_compass"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "evaluation"
    rl_tags: ClassVar[tuple[str, ...]] = ("prudex", "compass", "evaluation", "tmlr_2023")

    def __init__(self, *, periods_per_year: int = 252) -> None:
        self.periods_per_year = int(periods_per_year)

    def run(
        self,
        *,
        agent_results: dict[str, dict[str, Any]],
        benchmark_returns: np.ndarray | None = None,
    ) -> dict[str, Any]:
        """Compute per-agent metrics + rank matrix.

        Parameters
        ----------
        agent_results:
            Mapping ``agent_name -> {equity_curve, returns?, weights?,
            cross_dataset_sharpes?, regime_labels?}`` (per-key meaning
            matches :func:`compute_prudex_metrics`).
        benchmark_returns:
            Shared benchmark return series for the X-axis measures.
        """
        per_agent: dict[str, PrudexMetrics] = {}
        for name, payload in agent_results.items():
            eq = np.asarray(payload.get("equity_curve", []), dtype=np.float64)
            if eq.size < 2:
                continue
            metrics = compute_prudex_metrics(
                equity_curve=eq,
                returns=payload.get("returns"),
                weights_history=payload.get("weights_history"),
                cross_dataset_sharpes=payload.get("cross_dataset_sharpes"),
                regime_labels=payload.get("regime_labels"),
                periods_per_year=self.periods_per_year,
                benchmark_returns=benchmark_returns,
            )
            per_agent[name] = metrics

        if not per_agent:
            return PrudexReport(
                per_agent={},
                rank_matrix=np.zeros((0, 0), dtype=np.int64),
                metric_names=[],
            ).to_dict()

        metric_names = _metric_columns()
        rank_matrix = _rank_agents(per_agent, metric_names)
        report = PrudexReport(
            per_agent=per_agent,
            rank_matrix=rank_matrix,
            metric_names=metric_names,
            extras={"periods_per_year": self.periods_per_year},
        )
        return report.to_dict()


def _metric_columns() -> list[str]:
    """The canonical metric column order for the rank matrix."""
    return [
        "total_return",
        "sharpe_ratio",
        "annualised_return",
        "cagr",
        "sortino",
        "calmar",
        "max_drawdown",
        "volatility",
        "regime_conditioned_sharpe",
        "performance_profile_auc",
        "rank_score",
        "extreme_market_score",
        "portfolio_weight_entropy",
        "hit_rate",
    ]


def _rank_agents(
    per_agent: dict[str, PrudexMetrics],
    metric_names: list[str],
) -> np.ndarray:
    """Rank agents per metric (1 = best). Lower-is-better metrics (e.g.
    ``max_drawdown``, ``volatility``) get reversed before ranking."""
    lower_better = {"max_drawdown", "volatility"}
    names = list(per_agent.keys())
    n_agents = len(names)
    n_metrics = len(metric_names)
    rank_matrix = np.zeros((n_agents, n_metrics), dtype=np.int64)
    for j, metric in enumerate(metric_names):
        vals = np.asarray(
            [float(getattr(per_agent[n], metric, 0.0)) for n in names],
            dtype=np.float64,
        )
        if metric == "max_drawdown":
            # max_drawdown is already negative; "best" is closest to 0.
            order = np.argsort(-vals)  # descending: -0.05 (less negative) wins
        elif metric in lower_better:
            order = np.argsort(vals)  # ascending: smaller wins
        else:
            order = np.argsort(-vals)  # descending: larger wins
        for rank_pos, agent_idx in enumerate(order):
            rank_matrix[agent_idx, j] = rank_pos + 1
    return rank_matrix


__all__ = ["PrudexEvaluation"]
