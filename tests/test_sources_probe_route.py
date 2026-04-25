"""Tests for /sources probe route runtime adapter wiring."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def fastapi_test_client():
    fastapi = pytest.importorskip("fastapi.testclient")
    from aqp.api.main import app

    return fastapi.TestClient(app)


def _seed_source_row(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.routes import sources as sources_route

    monkeypatch.setattr(
        sources_route,
        "get_data_source",
        lambda name: {
            "name": name,
            "kind": "rest_api",
        },
    )


def _fake_httpx_client(payload: dict[str, Any]):
    class _FakeResponse:
        def __init__(self, body: dict[str, Any]) -> None:
            self._body = body

        def raise_for_status(self) -> None:
            return

        def json(self) -> dict[str, Any]:
            return self._body

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN201
            return False

        def get(self, url: str, params: dict[str, Any] | None = None) -> _FakeResponse:  # noqa: ARG002
            return _FakeResponse(payload)

    return _FakeClient


def test_alpha_vantage_probe_reports_missing_env_key(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_source_row(monkeypatch)
    monkeypatch.delenv("AQP_ALPHA_VANTAGE_API_KEY", raising=False)

    response = fastapi_test_client.get("/sources/alpha_vantage/probe")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "missing AQP_ALPHA_VANTAGE_API_KEY" in payload["message"]


def test_alpha_vantage_probe_uses_runtime_adapter(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.api.routes import sources as sources_route

    _seed_source_row(monkeypatch)
    monkeypatch.setenv("AQP_ALPHA_VANTAGE_API_KEY", "demo-key")
    monkeypatch.setattr(
        sources_route.httpx,
        "Client",
        _fake_httpx_client({"Global Quote": {"01. symbol": "IBM"}}),
    )

    response = fastapi_test_client.get("/sources/alpha_vantage/probe")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "reachable" in payload["message"]
    assert payload["details"]["symbol"] == "IBM"


def test_list_credentials_reads_env_file(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aqp.api.routes import sources as sources_route

    env_file = tmp_path / ".env"
    env_file.write_text("AQP_ALPHA_VANTAGE_API_KEY=alpha\n", encoding="utf-8")
    monkeypatch.setattr(sources_route, "_env_file_path", lambda: env_file)
    monkeypatch.setattr(
        sources_route,
        "_credential_key_index",
        lambda: {
            "AQP_ALPHA_VANTAGE_API_KEY": {"alpha_vantage"},
            "AQP_FRED_API_KEY": {"fred"},
        },
    )

    response = fastapi_test_client.get("/sources/credentials")
    assert response.status_code == 200
    payload = response.json()
    keys = [row["key"] for row in payload["credentials"]]
    assert keys == ["AQP_ALPHA_VANTAGE_API_KEY", "AQP_FRED_API_KEY"]
    alpha_row = next(row for row in payload["credentials"] if row["key"] == "AQP_ALPHA_VANTAGE_API_KEY")
    fred_row = next(row for row in payload["credentials"] if row["key"] == "AQP_FRED_API_KEY")
    assert alpha_row["value"] == "alpha"
    assert alpha_row["configured"] is True
    assert fred_row["value"] == ""
    assert fred_row["configured"] is False


def test_update_credentials_writes_env_and_runtime(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aqp.api.routes import sources as sources_route
    from aqp.config import settings

    env_file = tmp_path / ".env"
    monkeypatch.setattr(sources_route, "_env_file_path", lambda: env_file)
    monkeypatch.setattr(
        sources_route,
        "_credential_key_index",
        lambda: {
            "AQP_ALPHA_VANTAGE_API_KEY": {"alpha_vantage"},
            "AQP_SEC_EDGAR_IDENTITY": {"sec_edgar"},
        },
    )
    monkeypatch.setattr(settings, "sec_edgar_identity", "", raising=False)

    response = fastapi_test_client.put(
        "/sources/credentials",
        json={
            "values": {
                "AQP_ALPHA_VANTAGE_API_KEY": "new-key",
                "AQP_SEC_EDGAR_IDENTITY": "Jane Doe jane@example.com",
            }
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] == [
        "AQP_ALPHA_VANTAGE_API_KEY",
        "AQP_SEC_EDGAR_IDENTITY",
    ]
    content = env_file.read_text(encoding="utf-8")
    assert "AQP_ALPHA_VANTAGE_API_KEY=new-key" in content
    assert "AQP_SEC_EDGAR_IDENTITY=\"Jane Doe jane@example.com\"" in content
    assert sources_route.os.environ["AQP_ALPHA_VANTAGE_API_KEY"] == "new-key"
    assert settings.sec_edgar_identity == "Jane Doe jane@example.com"
