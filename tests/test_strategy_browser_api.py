"""Integration test for /strategies/browse — uses the FastAPI test client."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _app():
    pytest.importorskip("mlflow")
    from aqp.api.main import app

    return app


def test_strategy_browser_endpoint_exists() -> None:
    app = _app()
    client = TestClient(app)
    response = client.get("/strategies/browse")
    # DB may not be initialised in CI; we accept both 200 and 500, but the
    # route must exist.
    assert response.status_code in {200, 500}


def test_strategy_catalog_lists_alphas() -> None:
    app = _app()
    client = TestClient(app)
    response = client.get("/strategies/browse/catalog")
    assert response.status_code == 200
    payload = response.json()
    names = {row["alpha_class"] for row in payload}
    # At least a few of our shipped alphas must show up.
    for expected in (
        "AwesomeOscillatorAlpha",
        "HeikinAshiAlpha",
        "DualThrustAlpha",
        "SmaCross",
    ):
        assert expected in names


def test_ml_registered_endpoint() -> None:
    app = _app()
    client = TestClient(app)
    response = client.get("/ml/registered")
    assert response.status_code == 200
    data = response.json()
    assert "tree" in data
    assert "handlers" in data
