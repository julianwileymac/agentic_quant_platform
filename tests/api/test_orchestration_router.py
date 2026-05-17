from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from aqp.api.routes import orchestration

    app = FastAPI()
    app.include_router(orchestration.router, prefix="/api/v1/orchestration")
    return TestClient(app)


def test_airbyte_sync_calls_orchestrator(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.api.routes import orchestration

    seen: dict[str, object] = {}

    def _fake_trigger(self, connection_id: str, cursor_override=None):  # noqa: ANN001
        seen["connection_id"] = connection_id
        seen["cursor_override"] = cursor_override
        return "job-123"

    monkeypatch.setattr(
        orchestration.AirbyteOrchestrator,
        "trigger_sync",
        _fake_trigger,
    )

    response = client.post(
        "/api/v1/orchestration/airbyte/sync",
        json={"connection_id": "conn-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"job_id": "job-123"}
    assert seen["connection_id"] == "conn-1"
