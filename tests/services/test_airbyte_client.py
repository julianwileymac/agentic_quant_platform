from __future__ import annotations

import httpx

from aqp.services.airbyte_client import AirbyteClient, extract_job_id, normalize_job_status


class _ClientFactory:
    def __init__(self, client_cls, handler):
        self.client_cls = client_cls
        self.transport = httpx.MockTransport(handler)

    def __call__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        kwargs["transport"] = self.transport
        return self.client_cls(*args, **kwargs)


def test_airbyte_client_triggers_sync(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/public/v1/jobs"
        return httpx.Response(200, json={"jobId": "job-1", "status": "running"})

    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", _ClientFactory(original_client, handler))
    client = AirbyteClient(base_url="http://airbyte.test", token="")

    payload = client.trigger_sync("conn-1")

    assert payload["jobId"] == "job-1"
    assert extract_job_id(payload) == "job-1"
    assert normalize_job_status(payload).value == "running"


def test_airbyte_client_health_falls_back(monkeypatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(404, json={"error": "missing"})
        return httpx.Response(200, json={"ok": True})

    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", _ClientFactory(original_client, handler))
    client = AirbyteClient(base_url="http://airbyte.test", token="")

    assert client.health() == {"ok": True}
    assert calls[:2] == ["/api/public/v1/health", "/api/v1/health"]
