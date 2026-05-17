from __future__ import annotations

from contextlib import contextmanager
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(in_memory_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from aqp.api.routes import lineage

    Session = in_memory_db

    @contextmanager
    def _patched_get_session():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(lineage, "get_session", _patched_get_session)
    app = FastAPI()
    app.include_router(lineage.router, prefix="/api/v1/lineage")
    return TestClient(app)


def test_lineage_for_ledger_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/api/v1/lineage/ledger/missing-ledger")
    assert response.status_code == 404


def test_lineage_for_object_falls_back_when_versioning_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "aqp.data.fabric.versioning"
    monkeypatch.setitem(sys.modules, module_name, types.ModuleType(module_name))

    response = client.get("/api/v1/lineage/object/fabric-fallback")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["fabric_uuid"] == "fabric-fallback"
    assert payload["ok"] is None
    assert payload["snapshots"] == []
    assert payload["lineage_events"] == []


def test_lineage_for_object_calls_verify_lineage_chain(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def _fake_verify(fabric_uuid: str, *, session):  # noqa: ANN001
        seen["fabric_uuid"] = fabric_uuid
        return {"fabric_uuid": fabric_uuid, "ok": True, "lineage_events": []}

    monkeypatch.setattr(
        "aqp.data.fabric.versioning.verify_lineage_chain",
        _fake_verify,
        raising=True,
    )

    response = client.get("/api/v1/lineage/object/fabric-live")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert seen["fabric_uuid"] == "fabric-live"
    assert "ok" in payload
