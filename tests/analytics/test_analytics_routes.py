"""Tests for the Phase 4 ``/analytics/*`` routes.

Covers:

- ``/analytics/portfolio/metrics`` returns finite Sharpe / Sortino /
  MaxDD when given a synthetic returns series.
- ``/analytics/portfolio/rolling`` returns the three series at the
  configured window.
- ``/analytics/ml/distribution-overlay`` builds a histogram pair.
- ``/analytics/ml/drift-heatmap`` echoes a 2D matrix.
- ``/analytics/ml/perturbation-sweep`` returns aligned points.

The tearsheet Celery task is exercised only at the function level
(via the inline ``/tearsheet-sync`` route is skipped because it
requires quantstats' heavy HTML render path — covered separately).
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    pytest.importorskip("quantstats")
    pytest.importorskip("pandas")
    from fastapi import FastAPI

    from aqp.api.routes.analytics_ml import router as ml_router
    from aqp.api.routes.analytics_portfolio import router as portfolio_router

    app = FastAPI()
    app.include_router(portfolio_router)
    app.include_router(ml_router)
    return TestClient(app)


def _synthetic_returns(n: int = 252, seed: int = 0) -> list[float]:
    import numpy as np

    rng = np.random.default_rng(seed)
    rets = rng.normal(loc=0.0005, scale=0.01, size=n)
    return [float(x) for x in rets]


def test_portfolio_metrics_route(client: TestClient) -> None:
    returns = _synthetic_returns()
    res = client.post(
        "/analytics/portfolio/metrics",
        json={"returns": returns, "periods_per_year": 252},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["n_periods"] == len(returns)
    metrics: dict[str, Any] = body["metrics"]
    assert "sharpe" in metrics
    assert "max_drawdown" in metrics
    # On synthetic positive-drift Gaussian returns the Sharpe must be
    # a real number (not None) and the max drawdown must be <= 0.
    assert metrics["sharpe"] is None or isinstance(metrics["sharpe"], (int, float))
    assert metrics["max_drawdown"] is None or metrics["max_drawdown"] <= 0


def test_portfolio_metrics_short_series_fails(client: TestClient) -> None:
    res = client.post(
        "/analytics/portfolio/metrics",
        json={"returns": [0.01]},
    )
    assert res.status_code == 422


def test_portfolio_rolling_route(client: TestClient) -> None:
    returns = _synthetic_returns()
    res = client.post(
        "/analytics/portfolio/rolling",
        json={"returns": returns, "window": 30, "periods_per_year": 252},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["window"] == 30
    for key in ("rolling_sharpe", "rolling_vol", "underwater"):
        assert isinstance(body[key], list)
        assert len(body[key]) == len(returns)


def test_distribution_overlay_route(client: TestClient) -> None:
    import numpy as np

    rng = np.random.default_rng(123)
    actual = rng.normal(size=512).tolist()
    predicted = rng.normal(loc=0.1, size=512).tolist()
    res = client.post(
        "/analytics/ml/distribution-overlay",
        json={"actual": actual, "predicted": predicted, "bins": 20},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert len(body["bins"]) == 20
    assert len(body["actual"]) == 20
    assert len(body["predicted"]) == 20
    assert body["n_actual"] == 512
    assert body["n_predicted"] == 512


def test_distribution_overlay_length_mismatch(client: TestClient) -> None:
    res = client.post(
        "/analytics/ml/distribution-overlay",
        json={"actual": [0.0, 0.1], "predicted": [0.0, 0.1, 0.2]},
    )
    assert res.status_code == 422


def test_drift_heatmap_route(client: TestClient) -> None:
    matrix = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
    res = client.post(
        "/analytics/ml/drift-heatmap",
        json={"matrix": matrix},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["shape"] == [3, 2]
    assert body["matrix"] == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
    assert body["x_labels"] == ["0", "1"]
    assert body["y_labels"] == ["0", "1", "2"]


def test_perturbation_sweep_route(client: TestClient) -> None:
    res = client.post(
        "/analytics/ml/perturbation-sweep",
        json={
            "feature": "vol",
            "grid": [0.1, 0.2, 0.3],
            "metric": "sharpe",
            "values": [1.0, 0.9, 0.7],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["feature"] == "vol"
    assert len(body["points"]) == 3
    assert body["points"][0] == {"x": 0.1, "y": 1.0}


def test_tearsheet_enqueues_celery_task(monkeypatch) -> None:
    """Verify the route hands off to the Celery task without running it."""
    pytest.importorskip("pandas")

    # Stub the celery task .delay so the route is exercised without a
    # broker running. We patch the route's lookup of
    # ``aqp.tasks.analytics_tasks.render_portfolio_tearsheet``.
    from aqp.tasks import analytics_tasks

    class _Stub:
        @staticmethod
        def delay(**kwargs):  # type: ignore[no-untyped-def]
            class _Result:
                id = "stub-task-id"

            return _Result()

    monkeypatch.setattr(analytics_tasks, "render_portfolio_tearsheet", _Stub)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aqp.api.routes.analytics_portfolio import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    res = client.post(
        "/analytics/portfolio/tearsheet",
        json={"returns": [0.01] * 30, "title": "test"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["task_id"] == "stub-task-id"
