from __future__ import annotations

import httpx

from aqp.services.superset_client import SupersetClient


def test_superset_client_guest_token_flow() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/v1/security/login":
            return httpx.Response(200, json={"access_token": "access-1"})
        if request.url.path == "/api/v1/security/csrf_token/":
            assert request.headers["authorization"] == "Bearer access-1"
            return httpx.Response(200, json={"result": "csrf-1"})
        if request.url.path == "/api/v1/security/guest_token/":
            assert request.headers["x-csrftoken"] == "csrf-1"
            return httpx.Response(200, json={"token": "guest-1"})
        return httpx.Response(404, json={"error": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    superset = SupersetClient(
        base_url="http://superset.test",
        username="admin",
        password="admin",
        client=client,
    )

    token = superset.create_guest_token(resources=[{"type": "dashboard", "id": "dash-1"}])

    assert token == "guest-1"
    assert calls == [
        "/api/v1/security/login",
        "/api/v1/security/csrf_token/",
        "/api/v1/security/guest_token/",
    ]
