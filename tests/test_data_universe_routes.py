"""Route tests for managed universe endpoints."""
from __future__ import annotations

import pytest


@pytest.fixture
def fastapi_test_client():
    fastapi = pytest.importorskip("fastapi.testclient")
    from aqp.api.main import app

    return fastapi.TestClient(app)


def test_universe_sync_route_forwards_payload(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.api.routes import data as data_route

    captured: dict[str, tuple] = {}

    class _Result:
        id = "universe-task-1"

    def _delay(*args):
        captured["args"] = args
        return _Result()

    monkeypatch.setattr(data_route.sync_alpha_vantage_universe, "delay", _delay)

    response = fastapi_test_client.post(
        "/data/universe/sync",
        json={
            "state": "active",
            "limit": 50,
            "include_otc": True,
            "query": "AA",
        },
    )
    assert response.status_code == 200, response.text
    assert captured["args"] == ("active", 50, True, "AA")
    assert response.json()["task_id"] == "universe-task-1"


def test_universe_list_falls_back_to_config_when_snapshot_empty(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.api.routes import data as data_route
    from aqp.data.sources.alpha_vantage import universe as universe_mod

    class _EmptyService:
        def list_snapshot(self, *, limit: int = 200, query: str | None = None):  # noqa: ARG002
            return []

    monkeypatch.setattr(universe_mod, "AlphaVantageUniverseService", _EmptyService)
    monkeypatch.setattr(data_route.settings, "universe_provider", "managed_snapshot", raising=False)
    monkeypatch.setattr(data_route.settings, "default_universe", "AAPL,MSFT", raising=False)

    response = fastapi_test_client.get("/data/universe")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "config"
    assert payload["count"] == 2
    assert payload["items"][0]["ticker"] == "AAPL"


def test_universe_list_uses_managed_snapshot_when_available(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.api.routes import data as data_route
    from aqp.data.sources.alpha_vantage import universe as universe_mod

    class _SnapshotService:
        def list_snapshot(self, *, limit: int = 200, query: str | None = None):  # noqa: ARG002
            return [
                {
                    "id": "instrument-1",
                    "vt_symbol": "AAPL.NASDAQ",
                    "ticker": "AAPL",
                    "exchange": "NASDAQ",
                    "asset_class": "equity",
                    "security_type": "equity",
                    "sector": "Technology",
                    "industry": "Consumer Electronics",
                    "currency": "USD",
                    "updated_at": None,
                }
            ][:limit]

    monkeypatch.setattr(universe_mod, "AlphaVantageUniverseService", _SnapshotService)
    monkeypatch.setattr(data_route.settings, "universe_provider", "managed_snapshot", raising=False)

    response = fastapi_test_client.get("/data/universe")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "managed_snapshot"
    assert payload["count"] == 1
    assert payload["items"][0]["vt_symbol"] == "AAPL.NASDAQ"
