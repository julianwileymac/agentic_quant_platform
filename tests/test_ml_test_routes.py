"""API tests for the interactive ML testing endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(in_memory_db) -> TestClient:
    from aqp.api.main import app

    return TestClient(app)


def test_compare_endpoint_rejects_same_deployment(client: TestClient) -> None:
    res = client.post(
        "/ml/test/compare",
        json={
            "deployment_id_a": "x",
            "deployment_id_b": "x",
            "symbols": ["AAPL"],
        },
    )
    assert res.status_code == 400


def test_test_single_sync_invokes_task_path(monkeypatch, client: TestClient) -> None:
    """When sync=true the endpoint runs the task body in-process."""

    captured = {}

    def _fake(**kwargs):
        captured.update(kwargs)
        return {
            "deployment_id": kwargs["deployment_id"],
            "vt_symbol": kwargs.get("vt_symbol"),
            "prediction": 0.123,
            "feature_row": kwargs["feature_row"],
        }

    # Stub the real task body so we don't load a model.
    import aqp.tasks.ml_test_tasks as ml_test_tasks

    monkeypatch.setattr(
        ml_test_tasks.predict_single, "run", _fake, raising=False
    )

    res = client.post(
        "/ml/test/single",
        json={
            "deployment_id": "dep-1",
            "feature_row": {"f1": 0.1},
            "sync": True,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["prediction"] == 0.123
    assert captured["deployment_id"] == "dep-1"


def test_test_batch_async_returns_task(monkeypatch, client: TestClient) -> None:
    """sync=false dispatches to Celery and returns TaskAccepted."""

    class _AR:
        id = "task-async-1"

    def _fake_delay(*args, **kwargs):
        return _AR()

    import aqp.tasks.ml_test_tasks as ml_test_tasks

    monkeypatch.setattr(ml_test_tasks.predict_batch, "delay", _fake_delay)

    res = client.post(
        "/ml/test/batch",
        json={
            "deployment_id": "dep-1",
            "symbols": ["AAPL"],
            "start": "2024-01-01",
            "end": "2024-06-30",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["task_id"] == "task-async-1"
    assert body["stream_url"].endswith("task-async-1")
