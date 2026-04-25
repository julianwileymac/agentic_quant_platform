"""Smoke tests for ML planning and deployment endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _app():
    pytest.importorskip("mlflow")
    from aqp.api.main import app

    return app


def test_ml_planning_endpoints_exist() -> None:
    app = _app()
    client = TestClient(app)
    for path in (
        "/ml/split-plans",
        "/ml/pipelines",
        "/ml/experiments",
        "/ml/deployments",
        "/data/catalog",
    ):
        response = client.get(path)
        assert response.status_code in {200, 500}


def test_alpha_config_endpoint_exists() -> None:
    app = _app()
    client = TestClient(app)
    response = client.get("/ml/deployments/not-found/alpha-config")
    assert response.status_code in {404, 500}
