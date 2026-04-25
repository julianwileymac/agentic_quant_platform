"""Tests for the strategy persistence + versioning API."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(monkeypatch):
    # Patch Celery delay so /test doesn't hit Redis.
    from aqp.api import main as main_mod
    from aqp.tasks import backtest_tasks

    mock = MagicMock()
    mock.id = "fake-task-id"
    monkeypatch.setattr(backtest_tasks.run_backtest, "delay", lambda *a, **kw: mock)
    return TestClient(main_mod.app)


def _minimal_config_yaml() -> str:
    return """
strategy:
  class: FrameworkAlgorithm
  kwargs:
    universe_model:
      class: StaticUniverse
      kwargs: {symbols: [SPY]}
    alpha_model:
      class: MeanReversionAlpha
      kwargs: {lookback: 20, z_threshold: 2.0}
    portfolio_model:
      class: EqualWeightPortfolio
      kwargs: {max_positions: 1}
    risk_model:
      class: NoOpRiskModel
      kwargs: {}
    execution_model:
      class: MarketOrderExecution
      kwargs: {}
backtest:
  class: EventDrivenBacktester
  kwargs: {initial_cash: 100000, start: "2023-01-01", end: "2023-12-31"}
"""


def test_crud_flow(api_client):
    # Create
    resp = api_client.post(
        "/strategies/",
        json={
            "name": "test-strategy",
            "config_yaml": _minimal_config_yaml(),
            "author": "pytest",
        },
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()
    sid = created["id"]
    assert created["version"] == 1

    # Get detail
    resp = api_client.get(f"/strategies/{sid}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == sid
    assert len(detail["versions"]) == 1

    # Update → version 2
    resp = api_client.put(
        f"/strategies/{sid}",
        json={
            "config_yaml": _minimal_config_yaml().replace("lookback: 20", "lookback: 30"),
            "author": "pytest",
            "notes": "bumped lookback",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2

    # Diff
    resp = api_client.get(f"/strategies/{sid}/versions/2/diff?against=1")
    assert resp.status_code == 200
    diff = resp.json()
    assert "lookback" in diff["diff"]


def test_invalid_yaml_rejected(api_client):
    resp = api_client.post(
        "/strategies/",
        json={"name": "bad", "config_yaml": ":: not yaml ::"},
    )
    assert resp.status_code == 400


def test_list_empty_archive(api_client):
    resp = api_client.get("/strategies/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
