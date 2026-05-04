"""Smoke tests for the new API routes — exercises route registration,
schemas, and basic happy paths via FastAPI's TestClient with the
in-memory DB fixture.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def client(in_memory_db):
    from fastapi.testclient import TestClient

    # Importing the app triggers all router registrations.
    from aqp.api.main import app

    return TestClient(app)


def test_sinks_kinds_endpoint(client) -> None:
    r = client.get("/sinks/kinds")
    assert r.status_code == 200
    body = r.json()
    kinds = {row["kind"] for row in body}
    assert {"iceberg", "parquet", "kafka", "chroma", "profile"} <= kinds


def test_sinks_create_list_delete(client) -> None:
    r = client.post(
        "/sinks/",
        json={
            "name": "iceberg-bars",
            "kind": "iceberg",
            "display_name": "Iceberg bars",
            "config": {"namespace": "aqp", "table": "bars"},
            "tags": ["lakehouse"],
        },
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    listing = client.get("/sinks/").json()
    assert any(s["name"] == "iceberg-bars" for s in listing)

    versions = client.get(f"/sinks/{sid}/versions").json()
    assert len(versions) == 1

    materialised = client.post(f"/sinks/{sid}/materialise", json={"overrides": {}}).json()
    assert materialised["name"] == "sink.iceberg"

    deleted = client.delete(f"/sinks/{sid}")
    assert deleted.status_code == 204


def test_sources_setup_wizard_endpoints(client) -> None:
    r = client.get("/sources/wizards")
    assert r.status_code == 200
    keys = {w["source_key"] for w in r.json()}
    assert "alpha_vantage" in keys

    detail = client.get("/sources/alpha_vantage/setup-wizard").json()
    assert detail["source_key"] == "alpha_vantage"
    assert detail["steps"][0]["id"] == "intro"

    step = client.post(
        "/sources/alpha_vantage/setup-wizard",
        json={"step_id": "intro", "payload": {}},
    ).json()
    assert step["ok"] is True


def test_dataset_preset_wizard(client) -> None:
    detail = client.get("/dataset-presets/equity_universe_sp500_daily/wizard")
    assert detail.status_code == 200
    body = detail.json()
    assert body["preset_name"] == "equity_universe_sp500_daily"
    assert any(s["id"] == "review" for s in body["steps"])
    step = client.post(
        "/dataset-presets/equity_universe_sp500_daily/wizard/step",
        json={"step_id": "review", "payload": {}},
    ).json()
    assert step["ok"] is True


def test_streaming_kafka_proxy_fallback_503_when_unconfigured(client) -> None:
    # Both native and proxy unavailable -> 503.
    from aqp.config import settings

    settings.cluster_mgmt_url = ""
    r = client.get("/cluster-mgmt/kafka/topics")
    assert r.status_code == 503


def test_kafka_native_falls_back_when_no_dep(monkeypatch, client) -> None:
    """When confluent_kafka.admin is missing AND the proxy is unconfigured,
    the route surfaces a 503 so the UI can render a friendly message.
    """
    import aqp.streaming.admin.kafka_admin as ka

    def _raise() -> None:
        raise ka.KafkaAdminUnavailableError("no SDK")

    monkeypatch.setattr(ka, "get_kafka_admin", _raise)
    from aqp.config import settings

    settings.cluster_mgmt_url = ""
    r = client.get("/streaming/kafka/topics")
    assert r.status_code == 503


def test_producers_seed_and_list(client) -> None:
    r = client.get("/streaming/producers")
    assert r.status_code == 200
    body = r.json()
    names = {p["name"] for p in body}
    assert {"alphavantage", "ibkr", "alpaca"} <= names


def test_streaming_dataset_links_crud(client) -> None:
    r = client.post(
        "/datasets/test-dataset-id/streaming-links",
        json={
            "kind": "kafka_topic",
            "target_ref": "market.bar.v1",
            "direction": "source",
        },
    )
    assert r.status_code == 201, r.text
    link_id = r.json()["id"]

    listing = client.get("/datasets/test-dataset-id/streaming-links").json()
    assert any(item["id"] == link_id for item in listing)

    deleted = client.delete(f"/datasets/test-dataset-id/streaming-links/{link_id}")
    assert deleted.status_code == 204
