"""Tests for :mod:`aqp_cli.auth.device_flow` (AGENTS hard rule 53)."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from aqp_cli.auth.device_flow import (
    DeviceAuthorizationResponse,
    DeviceFlowClient,
    DeviceFlowError,
    DeviceFlowTokens,
    GRANT_TYPE_DEVICE_CODE,
)


@pytest.fixture
def mock_announce() -> list[str]:
    """Return a list that collects the announce_fn calls."""
    return []


@pytest.fixture
def make_client(mock_announce: list[str]):
    def _make(http_client: httpx.Client, *, sleep_fn=None) -> DeviceFlowClient:
        return DeviceFlowClient(
            domain="auth.example.com",
            client_id="cli_client_id",
            audience="https://api.example/",
            http_client=http_client,
            sleep_fn=sleep_fn or (lambda _seconds: None),
            announce_fn=lambda msg: mock_announce.append(msg),
            open_browser_fn=lambda _url: True,
        )

    return _make


def _http_handler(routes: list[tuple[str, httpx.Response]]) -> httpx.MockTransport:
    """Build a MockTransport that returns the queued responses in order."""

    iterator = iter(routes)

    def _handler(request: httpx.Request) -> httpx.Response:
        try:
            expected_path, response = next(iterator)
        except StopIteration as exc:
            raise AssertionError(f"unexpected request: {request.url}") from exc
        assert request.url.path == expected_path, (
            f"expected {expected_path!r} got {request.url.path!r}"
        )
        return response

    return httpx.MockTransport(_handler)


def test_request_device_code_round_trip(make_client) -> None:
    transport = _http_handler(
        [
            (
                "/oauth/device/code",
                httpx.Response(
                    200,
                    json={
                        "device_code": "device_abc",
                        "user_code": "ABCD-EFGH",
                        "verification_uri": "https://auth.example.com/activate",
                        "verification_uri_complete": "https://auth.example.com/activate?user_code=ABCD-EFGH",
                        "expires_in": 900,
                        "interval": 5,
                    },
                ),
            )
        ]
    )
    client = make_client(httpx.Client(transport=transport))
    response = client.request_device_code(scope="openid profile email")
    assert response.device_code == "device_abc"
    assert response.user_code == "ABCD-EFGH"
    assert response.interval == 5


def test_poll_for_tokens_authorization_pending_then_success(make_client) -> None:
    """Polling loop honours `authorization_pending` per RFC 8628 §3.5."""
    responses = [
        ("/oauth/token", httpx.Response(400, json={"error": "authorization_pending"})),
        ("/oauth/token", httpx.Response(400, json={"error": "authorization_pending"})),
        (
            "/oauth/token",
            httpx.Response(
                200,
                json={
                    "access_token": "good.access.token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "refresh_token": "good.refresh.token",
                    "id_token": "good.id.token",
                    "scope": "openid profile email",
                },
            ),
        ),
    ]
    sleep_calls: list[float] = []
    transport = _http_handler(responses)
    client = make_client(httpx.Client(transport=transport), sleep_fn=lambda s: sleep_calls.append(s))
    device = DeviceAuthorizationResponse(
        device_code="device_abc",
        user_code="ABCD-EFGH",
        verification_uri="https://auth.example.com/activate",
        verification_uri_complete=None,
        expires_in=900,
        interval=5,
    )
    tokens = client.poll_for_tokens(device)
    assert tokens.access_token == "good.access.token"
    assert tokens.refresh_token == "good.refresh.token"
    # All three sleeps used the base interval (no slow_down).
    assert sleep_calls == [5, 5, 5]


def test_poll_for_tokens_slow_down_increments_interval(make_client) -> None:
    """RFC 8628 §3.5: slow_down requires +5s on the interval."""
    responses = [
        ("/oauth/token", httpx.Response(400, json={"error": "slow_down"})),
        ("/oauth/token", httpx.Response(400, json={"error": "slow_down"})),
        (
            "/oauth/token",
            httpx.Response(
                200,
                json={"access_token": "x", "token_type": "Bearer", "expires_in": 3600},
            ),
        ),
    ]
    sleep_calls: list[float] = []
    client = make_client(
        httpx.Client(transport=_http_handler(responses)),
        sleep_fn=lambda s: sleep_calls.append(s),
    )
    device = DeviceAuthorizationResponse(
        device_code="d",
        user_code="C",
        verification_uri="u",
        verification_uri_complete=None,
        expires_in=900,
        interval=5,
    )
    client.poll_for_tokens(device)
    # 5 (initial) -> 10 (first slow_down) -> 15 (second slow_down)
    assert sleep_calls == [5, 10, 15]


def test_poll_for_tokens_access_denied_raises(make_client) -> None:
    responses = [
        (
            "/oauth/token",
            httpx.Response(
                400,
                json={"error": "access_denied", "error_description": "user said no"},
            ),
        ),
    ]
    client = make_client(
        httpx.Client(transport=_http_handler(responses)),
    )
    device = DeviceAuthorizationResponse(
        device_code="d",
        user_code="C",
        verification_uri="u",
        verification_uri_complete=None,
        expires_in=900,
        interval=5,
    )
    with pytest.raises(DeviceFlowError) as exc_info:
        client.poll_for_tokens(device)
    assert exc_info.value.code == "access_denied"


def test_refresh_exchanges_refresh_token(make_client) -> None:
    transport = _http_handler(
        [
            (
                "/oauth/token",
                httpx.Response(
                    200,
                    json={
                        "access_token": "fresh.token",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                        "refresh_token": "new.refresh",
                    },
                ),
            )
        ]
    )
    client = make_client(httpx.Client(transport=transport))
    tokens = client.refresh("old.refresh")
    assert tokens.access_token == "fresh.token"
    # Refresh token rotation — new one returned overrides the original.
    assert tokens.refresh_token == "new.refresh"


def test_refresh_falls_back_to_original_refresh_token(make_client) -> None:
    transport = _http_handler(
        [
            (
                "/oauth/token",
                httpx.Response(
                    200,
                    json={
                        "access_token": "fresh",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                        # NO refresh_token in response — keep the original.
                    },
                ),
            )
        ]
    )
    client = make_client(httpx.Client(transport=transport))
    tokens = client.refresh("original.refresh")
    assert tokens.refresh_token == "original.refresh"
