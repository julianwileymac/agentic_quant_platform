"""Verify every new API route the UI depends on is present."""
from __future__ import annotations


def _paths() -> set[str]:
    from aqp.api.main import app

    return {getattr(r, "path", "") for r in app.routes}


def test_new_ui_endpoints_exist() -> None:
    paths = _paths()
    # Phase 5a — Indicator Builder
    assert "/data/indicators" in paths
    assert "/data/indicators/preview" in paths
    # Phase 3b — Factor Workbench
    assert "/factors/operators" in paths
    assert "/factors/preview" in paths
    # Phase 5b — Optimizer
    assert "/backtest/optimize" in paths
    assert "/backtest/optimize/{run_id}" in paths
    assert "/backtest/optimize/{run_id}/results" in paths
    # Phase 5c — Crew Trace registry
    assert "/agents/crews" in paths
    assert "/agents/crews/{task_id}" in paths
    assert "/agents/crews/{task_id}/events" in paths
    # Phase 5d — ML Model Detail
    assert "/ml/models/{model_id}/details" in paths
    # Quant ML planning + deployment
    assert "/ml/split-plans" in paths
    assert "/ml/split-plans/{plan_id}" in paths
    assert "/ml/pipelines" in paths
    assert "/ml/pipelines/{pipeline_id}" in paths
    assert "/ml/experiments" in paths
    assert "/ml/experiments/{experiment_id}" in paths
    assert "/ml/deployments" in paths
    assert "/ml/deployments/{deployment_id}" in paths
    assert "/ml/deployments/{deployment_id}/alpha-config" in paths
    assert "/data/catalog" in paths
    assert "/data/catalog/{catalog_id}/versions" in paths
    assert "/data/ibkr/historical/fetch" in paths
    assert "/data/ibkr/historical/ingest" in paths
    assert "/data/ibkr/historical/availability" in paths


def test_existing_core_endpoints_still_present() -> None:
    """Regression guard — refactoring the routes file should not drop pre-existing paths."""
    paths = _paths()
    for required in (
        "/health",
        "/chat",
        "/chat/stream/{task_id}",
        "/agents/crew/run",
        "/backtest/run",
        "/backtest/walk_forward",
        "/backtest/monte_carlo",
        "/backtest/runs",
        "/rl/train",
        "/data/ingest",
        "/data/search",
        "/data/describe",
        "/portfolio/orders",
        "/portfolio/kill_switch",
        "/paper/start",
        "/paper/runs",
        "/factors/evaluate",
        "/brokers/",
        "/brokers/schema",
        "/ml/train",
        "/ml/models",
        "/strategies/",
        "/strategies/browse",
        "/strategies/browse/catalog",
        "/live/subscribe",
    ):
        assert required in paths, f"{required} missing from the API surface"
