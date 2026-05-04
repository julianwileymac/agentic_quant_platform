"""Hermetic API tests for the alpha-backtest endpoints."""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(in_memory_db) -> TestClient:
    from aqp.api.main import app

    return TestClient(app)


def test_alpha_backtest_endpoint_validates_train_payload(client: TestClient) -> None:
    res = client.post(
        "/ml/alpha-backtest-runs",
        json={
            "strategy_cfg": {"class": "Strategy"},
            "backtest_cfg": {"class": "Engine"},
            "train_first": True,
        },
    )
    assert res.status_code == 400
    assert "dataset_cfg" in res.text


def test_alpha_backtest_endpoint_validates_existing_payload(client: TestClient) -> None:
    res = client.post(
        "/ml/alpha-backtest-runs",
        json={
            "strategy_cfg": {"class": "Strategy"},
            "backtest_cfg": {"class": "Engine"},
            "train_first": False,
        },
    )
    assert res.status_code == 400
    assert "deployment_id" in res.text


def test_list_alpha_backtest_runs_empty(client: TestClient) -> None:
    res = client.get("/ml/alpha-backtest-runs")
    assert res.status_code == 200
    assert res.json() == []


def test_get_alpha_backtest_run_404(client: TestClient) -> None:
    res = client.get("/ml/alpha-backtest-runs/missing-id")
    assert res.status_code == 404


def test_alpha_backtest_run_lifecycle_persistence(in_memory_db, client: TestClient) -> None:
    """Insert a row and verify GET endpoints surface it."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models import MLAlphaBacktestRun

    with get_session() as session:
        row = MLAlphaBacktestRun(
            run_name="manual-row",
            status="completed",
            ml_metrics={"ic_spearman": 0.4},
            trading_metrics={"sharpe": 1.3},
            combined_metrics={"score": 0.85, "sharpe": 1.3},
            attribution={"available": True},
            mlflow_run_id="r-1",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        row_id = row.id

    list_res = client.get("/ml/alpha-backtest-runs")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["id"] == row_id
    assert list_res.json()[0]["combined_metrics"]["sharpe"] == 1.3

    get_res = client.get(f"/ml/alpha-backtest-runs/{row_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == row_id
