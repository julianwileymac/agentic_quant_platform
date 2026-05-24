"""PRUDEX-Compass visualisation primitives.

Five rendering helpers — each takes the relevant slice of a
:class:`PrudexReport` and returns a matplotlib :class:`Figure`. The
caller can choose to render inline (``fig.show()``), save to disk
(``fig.savefig(path)``), or pickle into the MLflow artefact store.

The renderers degrade gracefully — when matplotlib is unavailable
they return a dict-shaped fallback (``{"data": [...], "layout":
{...}}``) suitable for the lab UI's Plotly renderer.

Functions
=========

- :func:`pride_star_chart` — 8-axis radar of per-agent scores.
- :func:`prudex_compass_chart` — 6-axis octagon (inner/outer slice).
- :func:`performance_profile_chart` — CDF performance profile across
  agents.
- :func:`rank_distribution_chart` — rank heatmap across metrics.
- :func:`extreme_market_chart` — TR/SR comparison in extreme market
  windows.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from aqp_rl.evaluation.prudex_compass import PrudexReport

logger = logging.getLogger(__name__)


def _maybe_matplotlib() -> Any | None:
    try:
        import matplotlib.pyplot as plt  # noqa: PLC0415

        return plt
    except Exception:  # noqa: BLE001
        return None


def pride_star_chart(report: PrudexReport, *, ax: Any | None = None) -> Any:
    """Polar/radar plot of 8 PRUDEX scalar measures per agent."""
    plt = _maybe_matplotlib()
    measures = [
        "total_return",
        "sharpe_ratio",
        "annualised_return",
        "sortino",
        "calmar",
        "hit_rate",
        "portfolio_weight_entropy",
        "regime_conditioned_sharpe",
    ]
    if plt is None:
        return {
            "type": "radar",
            "measures": measures,
            "per_agent": {
                name: [getattr(m, k, 0.0) for k in measures]
                for name, m in report.per_agent.items()
            },
        }
    fig = None
    if ax is None:
        fig, ax = plt.subplots(subplot_kw={"projection": "polar"})
    angles = np.linspace(0, 2 * np.pi, len(measures), endpoint=False).tolist()
    angles += angles[:1]
    for name, metrics in report.per_agent.items():
        values = [float(getattr(metrics, m, 0.0)) for m in measures]
        values += values[:1]
        ax.plot(angles, values, label=name)
        ax.fill(angles, values, alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(measures)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
    return fig if fig is not None else ax


def prudex_compass_chart(report: PrudexReport, *, ax: Any | None = None) -> Any:
    """6-axis PRUDEX octagon (one axis per PRUDEX axis P/R/U/D/E/X)."""
    plt = _maybe_matplotlib()
    axis_names = ["P", "R", "U", "D", "E", "X"]
    per_agent_axes = {
        name: _axis_scores(metrics) for name, metrics in report.per_agent.items()
    }
    if plt is None:
        return {
            "type": "compass",
            "axes": axis_names,
            "per_agent": per_agent_axes,
        }
    fig = None
    if ax is None:
        fig, ax = plt.subplots(subplot_kw={"projection": "polar"})
    angles = np.linspace(0, 2 * np.pi, len(axis_names), endpoint=False).tolist()
    angles += angles[:1]
    for name, scores in per_agent_axes.items():
        vals = list(scores) + scores[:1]
        ax.plot(angles, vals, label=name)
        ax.fill(angles, vals, alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(axis_names)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
    return fig if fig is not None else ax


def performance_profile_chart(
    per_agent_returns: dict[str, np.ndarray],
    *,
    ax: Any | None = None,
) -> Any:
    """Per-agent empirical CDF of returns (rliable performance profile)."""
    plt = _maybe_matplotlib()
    if plt is None:
        return {
            "type": "performance_profile",
            "per_agent": {k: v.tolist() for k, v in per_agent_returns.items()},
        }
    fig = None
    if ax is None:
        fig, ax = plt.subplots()
    for name, returns in per_agent_returns.items():
        r = np.asarray(returns, dtype=np.float64)
        if r.size == 0:
            continue
        sorted_r = np.sort(r)
        cdf = np.arange(1, len(sorted_r) + 1) / len(sorted_r)
        ax.plot(sorted_r, 1 - cdf, label=name)
    ax.set_xlabel("return")
    ax.set_ylabel("P(R ≥ r)")
    ax.set_title("Performance Profile")
    ax.legend()
    return fig if fig is not None else ax


def rank_distribution_chart(report: PrudexReport, *, ax: Any | None = None) -> Any:
    """Heatmap of per-metric ranks across agents."""
    plt = _maybe_matplotlib()
    agents = list(report.per_agent.keys())
    if plt is None:
        return {
            "type": "rank_distribution",
            "agents": agents,
            "metric_names": list(report.metric_names),
            "ranks": report.rank_matrix.tolist(),
        }
    fig = None
    if ax is None:
        fig, ax = plt.subplots()
    im = ax.imshow(report.rank_matrix, aspect="auto", cmap="viridis")
    ax.set_yticks(range(len(agents)))
    ax.set_yticklabels(agents)
    ax.set_xticks(range(len(report.metric_names)))
    ax.set_xticklabels(report.metric_names, rotation=45, ha="right")
    if fig is not None:
        fig.colorbar(im, ax=ax, label="rank (lower = better)")
    return fig if fig is not None else ax


def extreme_market_chart(
    per_agent_extreme_scores: dict[str, float],
    *,
    ax: Any | None = None,
) -> Any:
    """Bar chart of per-agent cumulative returns in extreme market windows."""
    plt = _maybe_matplotlib()
    if plt is None:
        return {
            "type": "extreme_market",
            "per_agent": dict(per_agent_extreme_scores),
        }
    fig = None
    if ax is None:
        fig, ax = plt.subplots()
    names = list(per_agent_extreme_scores.keys())
    values = [per_agent_extreme_scores[n] for n in names]
    ax.bar(names, values)
    ax.set_ylabel("cumulative return in worst-decile periods")
    ax.set_title("Performance under Extreme Markets")
    ax.axhline(0, color="black", linewidth=0.5)
    return fig if fig is not None else ax


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _axis_scores(metrics) -> list[float]:
    """Collapse the per-axis metric breakdown into a single 6-tuple of scores."""
    per_axis = metrics.per_axis()
    return [
        float(np.mean(list(per_axis[axis].values()))) for axis in ("P", "R", "U", "D", "E", "X")
    ]


__all__ = [
    "extreme_market_chart",
    "performance_profile_chart",
    "pride_star_chart",
    "prudex_compass_chart",
    "rank_distribution_chart",
]
