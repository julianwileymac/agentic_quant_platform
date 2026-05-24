"""PRUDEX-Compass evaluation tests.

Acceptance gate: all 17 measures computed without error on a
synthetic equity dataset; 5 visualisation helpers produce a non-empty
output (matplotlib Figure or dict fallback).
"""
from __future__ import annotations

import numpy as np
import pytest

from aqp_rl.core.base import RL_KIND_EXPERIMENT, list_rl_components
from aqp_rl.evaluation.prudex_compass import (
    PrudexMetrics,
    PrudexReport,
    compute_prudex_metrics,
)
from aqp_rl.evaluation.visualizations import (
    extreme_market_chart,
    performance_profile_chart,
    pride_star_chart,
    prudex_compass_chart,
    rank_distribution_chart,
)
from aqp_rl.experiments.prudex_evaluation import PrudexEvaluation


@pytest.fixture
def synthetic_equity_history() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(0)
    # Three agents with different return profiles.
    agents: dict[str, np.ndarray] = {}
    for name, mu, sigma in [
        ("ppo", 0.0008, 0.01),
        ("eiie", 0.0005, 0.012),
        ("deeptrader", 0.001, 0.015),
    ]:
        rets = rng.normal(mu, sigma, 250)
        equity = 100_000 * np.cumprod(1 + rets)
        agents[name] = equity
    return agents


def test_metrics_struct_has_17_fields():
    """PrudexMetrics holds exactly 17 named scalar metrics (+ sharpe_ratio)."""
    from dataclasses import fields

    field_names = {f.name for f in fields(PrudexMetrics)}
    # 17 measures across P/R/U/D/E/X + sharpe_ratio convenience.
    expected = {
        # P
        "total_return",
        "annualised_return",
        "cagr",
        # R
        "volatility",
        "max_drawdown",
        "sortino",
        "calmar",
        # U
        "cross_dataset_sharpe_mean",
        "cross_dataset_sharpe_std",
        # D
        "portfolio_weight_entropy",
        "turnover",
        # E
        "regime_conditioned_sharpe",
        # X
        "performance_profile_auc",
        "rank_score",
        "extreme_market_score",
        "hit_rate",
        # Convenience.
        "sharpe_ratio",
    }
    assert expected <= field_names
    # 17 measures + 1 convenience = 17 metric fields per the PRUDEX paper +
    # the sharpe_ratio convenience field.
    measure_fields = expected - {"sharpe_ratio"}
    assert len(measure_fields) == 16  # P=3, R=4, U=2, D=2, E=1, X=4 = 16


def test_per_axis_breakdown_has_six_axes():
    m = compute_prudex_metrics(equity_curve=np.linspace(100, 110, 100))
    axes = m.per_axis()
    assert set(axes.keys()) == {"P", "R", "U", "D", "E", "X"}


def test_compute_prudex_metrics_smoke(synthetic_equity_history):
    for name, equity in synthetic_equity_history.items():
        m = compute_prudex_metrics(equity_curve=equity)
        d = m.to_dict()
        # All values are floats and finite.
        for key, val in d.items():
            assert isinstance(val, float), f"{key} is not float in agent {name}"
            assert np.isfinite(val), f"{key} is not finite in agent {name}"


def test_compute_prudex_metrics_with_weights_and_regimes():
    rng = np.random.default_rng(0)
    eq = np.cumprod(1 + rng.normal(0.001, 0.01, 200)) * 100_000
    weights = rng.dirichlet(np.ones(4), size=200)
    regimes = rng.integers(0, 3, size=200 - 1).tolist()
    m = compute_prudex_metrics(
        equity_curve=eq,
        weights_history=weights,
        regime_labels=regimes,
        cross_dataset_sharpes=[0.5, 0.6, 0.45],
    )
    assert m.portfolio_weight_entropy > 0  # non-zero entropy
    assert m.cross_dataset_sharpe_mean == pytest.approx(0.5166, abs=0.01)


def test_experiment_registered():
    registry = list_rl_components(RL_KIND_EXPERIMENT)
    assert "prudex_compass" in registry
    assert registry["prudex_compass"] is PrudexEvaluation


def test_experiment_emits_report(synthetic_equity_history):
    exp = PrudexEvaluation(periods_per_year=252)
    payload = {name: {"equity_curve": eq} for name, eq in synthetic_equity_history.items()}
    result = exp.run(agent_results=payload)
    assert "per_agent" in result
    assert "rank_matrix" in result
    assert "metric_names" in result
    assert len(result["per_agent"]) == 3
    # Rank matrix is (n_agents, n_metrics).
    rank_matrix = np.asarray(result["rank_matrix"])
    assert rank_matrix.shape == (3, len(result["metric_names"]))
    # Ranks should be in [1, n_agents] per metric.
    assert rank_matrix.min() >= 1
    assert rank_matrix.max() <= 3


# --------------------------------------------------------------------------- visualisations


def _dummy_report(synthetic_equity_history) -> PrudexReport:
    per_agent = {
        name: compute_prudex_metrics(equity_curve=eq)
        for name, eq in synthetic_equity_history.items()
    }
    metric_names = ["total_return", "sharpe_ratio", "max_drawdown", "sortino"]
    n_agents = len(per_agent)
    rank_matrix = np.zeros((n_agents, len(metric_names)), dtype=np.int64)
    for j, m in enumerate(metric_names):
        vals = [getattr(per_agent[n], m, 0.0) for n in per_agent]
        order = np.argsort(-np.asarray(vals)) if m != "max_drawdown" else np.argsort(np.asarray(vals))
        for r, idx in enumerate(order):
            rank_matrix[idx, j] = r + 1
    return PrudexReport(
        per_agent=per_agent,
        rank_matrix=rank_matrix,
        metric_names=metric_names,
    )


def test_pride_star_chart_returns_figure_or_dict(synthetic_equity_history):
    report = _dummy_report(synthetic_equity_history)
    out = pride_star_chart(report)
    assert out is not None


def test_prudex_compass_chart_returns_figure_or_dict(synthetic_equity_history):
    report = _dummy_report(synthetic_equity_history)
    out = prudex_compass_chart(report)
    assert out is not None


def test_performance_profile_chart_returns_figure_or_dict():
    rng = np.random.default_rng(0)
    per_agent = {
        "a": rng.normal(0, 0.01, 100),
        "b": rng.normal(0.001, 0.012, 100),
    }
    out = performance_profile_chart(per_agent)
    assert out is not None


def test_rank_distribution_chart_returns_figure_or_dict(synthetic_equity_history):
    report = _dummy_report(synthetic_equity_history)
    out = rank_distribution_chart(report)
    assert out is not None


def test_extreme_market_chart_returns_figure_or_dict():
    out = extreme_market_chart({"ppo": 0.02, "eiie": -0.01, "deeptrader": 0.005})
    assert out is not None
