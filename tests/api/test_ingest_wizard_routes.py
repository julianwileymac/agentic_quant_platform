"""Tests for the ingest wizard orchestration routes."""
from __future__ import annotations

from datetime import datetime

import pytest


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aqp.api.routes.ingest_wizard import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_bootstrap_aggregates_dependencies(monkeypatch: pytest.MonkeyPatch, client) -> None:
    from aqp.api.routes import ingest_wizard as routes

    class _Obj:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def to_dict(self) -> dict[str, object]:
            return dict(self._payload)

    class _Template:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            _ = mode
            return dict(self._payload)

    monkeypatch.setattr(
        routes,
        "list_data_sources",
        lambda enabled_only=False: [  # noqa: ARG005
            {"name": "alpha_vantage", "enabled": True},
        ],
    )
    monkeypatch.setattr(
        routes,
        "list_wizards",
        lambda: [
            _Obj({"source_key": "alpha_vantage", "display_name": "Alpha Vantage"}),
        ],
    )
    monkeypatch.setattr(
        routes,
        "list_presets",
        lambda: [
            _Obj({"name": "equity_universe_sp500_daily", "source_kind": "alpha_vantage"}),
        ],
    )
    monkeypatch.setattr(
        routes,
        "list_loading_templates",
        lambda: [
            _Template({"id": "alpha-vantage-delta", "run_kind": "alpha_vantage_intraday_delta"}),
        ],
    )
    monkeypatch.setattr(
        routes.service_manager,
        "health",
        lambda: {"ok": True, "services": {"airbyte": {"ok": True}}, "config": {}},
    )
    monkeypatch.setattr(
        routes.compute_routes,
        "status",
        lambda: {"dask": {"available": True}, "ray": {"available": False}},
    )
    monkeypatch.setattr(
        routes,
        "_queue_snapshot",
        lambda: routes.QueueSnapshot(
            workers_seen=1,
            active=1,
            reserved=0,
            scheduled=0,
            queued=0,
            total=1,
            ingestion_active=1,
            ingestion_reserved=0,
            ingestion_scheduled=0,
            ingestion_queued=0,
        ),
    )

    resp = client.get("/ingest/wizard/bootstrap")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sources"][0]["name"] == "alpha_vantage"
    assert body["source_wizards"][0]["source_key"] == "alpha_vantage"
    assert body["dataset_presets"][0]["name"] == "equity_universe_sp500_daily"
    assert body["loading_templates"][0]["id"] == "alpha-vantage-delta"
    assert body["queue"]["workers_seen"] == 1
    assert body["service_health"]["ok"] is True


def test_preflight_flags_missing_credentials(monkeypatch: pytest.MonkeyPatch, client) -> None:
    from aqp.api.routes import ingest_wizard as routes
    from aqp.api.routes import sources as sources_routes

    monkeypatch.setattr(
        routes.sources_routes,
        "list_credentials",
        lambda: sources_routes.CredentialsResponse(
            env_file=".env",
            credentials=[
                sources_routes.CredentialEntry(
                    key="AQP_ALPHA_VANTAGE_API_KEY",
                    value="",
                    configured=False,
                    used_by=["alpha_vantage"],
                )
            ],
        ),
    )

    resp = client.post(
        "/ingest/wizard/preflight",
        json={
            "required_credentials": ["AQP_ALPHA_VANTAGE_API_KEY"],
            "run_service_health": False,
            "run_compute_status": False,
            "run_queue_snapshot": False,
            "run_source_probe": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    checks = {entry["check_id"]: entry for entry in body["checks"]}
    cred = checks["credential-presence"]
    assert cred["ok"] is False
    assert cred["severity"] == "error"
    assert "AQP_ALPHA_VANTAGE_API_KEY" in cred["details"]["missing"]


def test_recommendation_handles_high_queue_pressure(monkeypatch: pytest.MonkeyPatch, client) -> None:
    from aqp.api.routes import ingest_wizard as routes

    monkeypatch.setattr(
        routes,
        "_queue_snapshot",
        lambda: routes.QueueSnapshot(
            workers_seen=2,
            active=10,
            reserved=8,
            scheduled=8,
            queued=16,
            total=26,
            ingestion_active=8,
            ingestion_reserved=8,
            ingestion_scheduled=8,
            ingestion_queued=16,
        ),
    )
    monkeypatch.setattr(
        routes.service_manager,
        "health",
        lambda: {"ok": True, "services": {}, "config": {}},
    )
    monkeypatch.setattr(
        routes.compute_routes,
        "status",
        lambda: {
            "local": {"available": True},
            "dask": {"available": True},
            "ray": {"available": True},
        },
    )
    monkeypatch.setattr(
        routes,
        "get_data_source",
        lambda name: {  # noqa: ARG005
            "name": "alpha_vantage",
            "rate_limits": {"requests_per_minute": 10, "requests_per_day": 500},
        },
    )
    monkeypatch.setattr(
        routes,
        "datetime",
        type(
            "_FixedDatetime",
            (),
            {"utcnow": staticmethod(lambda: datetime(2026, 1, 1, 0, 0, 0))},
        ),
    )

    resp = client.post(
        "/ingest/wizard/recommend",
        json={
            "source_name": "alpha_vantage",
            "estimated_rows": 5_000_000,
            "estimated_bytes": 2_000_000_000,
            "desired_rpm": 40,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["queue_strategy"]["pressure"] == "high"
    assert body["queue_strategy"]["recommended_parallel_runs"] == 1
    assert body["rate_limit"]["provider_rpm"] == 10
    # Provider cap is 10 RPM, then queue-pressure cut applies.
    assert body["rate_limit"]["recommended_rpm"] == 5
    advisory_messages = [entry["message"] for entry in body["advisories"]]
    assert any("Queue pressure is high" in msg for msg in advisory_messages)
    assert any("exceeds provider limit" in msg for msg in advisory_messages)
