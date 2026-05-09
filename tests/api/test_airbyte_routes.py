from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_airbyte_health_when_disabled(monkeypatch) -> None:
    from aqp.api.routes import airbyte

    monkeypatch.setattr(airbyte.settings, "airbyte_enabled", False)
    monkeypatch.setattr(airbyte.settings, "airbyte_base_url", "http://example.invalid:8001")

    payload = airbyte.health()

    assert payload["ok"] is False
    assert payload["enabled"] is False
    assert payload["airbyte"]["reachable"] is False
    assert "AQP_AIRBYTE_ENABLED" in payload["airbyte"]["detail"]


def _build_client() -> TestClient:
    from aqp.api.routes import airbyte

    app = FastAPI()
    app.include_router(airbyte.router)
    return TestClient(app)


def test_airbyte_market_connectors_exposed_by_api() -> None:
    client = _build_client()
    response = client.get("/airbyte/connectors", params={"kind": "source"})
    response.raise_for_status()
    ids = {row["id"] for row in response.json()}

    assert {
        "alpha-vantage",
        "yfinance",
        "fred",
        "ibkr-historical",
        "sec",
    } <= ids


def test_airbyte_connector_entity_mappings_include_new_market_set() -> None:
    client = _build_client()

    yfinance_resp = client.get("/airbyte/connectors/yfinance/entity-mappings")
    yfinance_resp.raise_for_status()
    yfinance_streams = {row["stream"] for row in yfinance_resp.json()["mappings"]}
    assert {"ohlcv_bars", "fundamentals"} <= yfinance_streams

    ibkr_resp = client.get("/airbyte/connectors/ibkr-historical/entity-mappings")
    ibkr_resp.raise_for_status()
    ibkr_streams = {row["stream"] for row in ibkr_resp.json()["mappings"]}
    assert {"historical_bars", "contracts"} <= ibkr_streams
