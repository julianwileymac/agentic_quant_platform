"""Tests for :mod:`aqp.auth.token_exchange` (AGENTS hard rule 54)."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from aqp.auth.token_exchange import (
    DEFAULT_AGENT_SCOPES,
    DEFAULT_PROFILE_NAME,
    DelegatedToken,
    TokenExchangeBroker,
    TokenExchangeError,
    reset_token_exchange_broker,
)


@pytest.fixture(autouse=True)
def _reset_broker() -> None:
    reset_token_exchange_broker()
    yield
    reset_token_exchange_broker()


def _settings_with(**overrides: Any) -> Any:
    """Patch ``settings`` to return a stub with the requested overrides."""

    from aqp.config import settings as real_settings

    stub = type("StubSettings", (), {})()
    # Copy the bare-minimum fields the broker reads.
    stub.auth_agent_token_exchange_enabled = True
    stub.auth_oidc_issuer = "https://auth.example/"
    stub.auth_oidc_audience = "https://api.example/"
    stub.auth_agent_broker_client_id = "broker_client_id"
    stub.auth_agent_broker_client_secret = "broker_secret"
    stub.auth_agent_delegation_ttl_seconds = 300
    for k, v in overrides.items():
        setattr(stub, k, v)
    return stub


def test_is_enabled_requires_all_fields() -> None:
    broker = TokenExchangeBroker()
    with patch("aqp.auth.token_exchange.settings", _settings_with()):
        assert broker.is_enabled() is True
    with patch(
        "aqp.auth.token_exchange.settings",
        _settings_with(auth_agent_token_exchange_enabled=False),
    ):
        assert broker.is_enabled() is False
    with patch(
        "aqp.auth.token_exchange.settings",
        _settings_with(auth_agent_broker_client_id=""),
    ):
        assert broker.is_enabled() is False


def test_mint_for_agent_returns_none_when_disabled() -> None:
    broker = TokenExchangeBroker()
    with patch(
        "aqp.auth.token_exchange.settings",
        _settings_with(auth_agent_token_exchange_enabled=False),
    ):
        result = broker.mint_for_agent(
            user_access_token="user_jwt",
            agent_actor_token="actor_jwt",
            agent_subject="agent|research_lead",
            user_subject="auth0|user123",
        )
    assert result is None


def test_mint_for_agent_calls_token_endpoint_with_rfc8693_shape() -> None:
    captured: dict[str, Any] = {}

    def fake_post(self, url, *, data, headers, **kwargs) -> httpx.Response:  # noqa: ARG001
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return httpx.Response(
            status_code=200,
            request=httpx.Request("POST", url),
            json={
                "access_token": "delegated.jwt.signature",
                "token_type": "Bearer",
                "expires_in": 300,
                "scope": "read:mcp:data write:mcp:data",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    broker = TokenExchangeBroker(http_client=client)
    with patch.object(httpx.Client, "post", fake_post), patch(
        "aqp.auth.token_exchange.settings", _settings_with()
    ):
        result = broker.mint_for_agent(
            user_access_token="user_jwt",
            agent_actor_token="actor_jwt",
            agent_subject="agent|research_lead",
            user_subject="auth0|user123",
            scopes=("read:mcp:data", "write:mcp:data"),
        )
    assert result is not None
    assert result.access_token == "delegated.jwt.signature"
    assert result.act_sub == "agent|research_lead"
    assert result.on_behalf_of_sub == "auth0|user123"
    assert result.audience == "https://api.example/"

    # Verify wire shape (RFC 8693).
    assert captured["url"].endswith("/oauth/token")
    body = captured["data"]
    assert body["grant_type"] == "urn:ietf:params:oauth:grant-type:token-exchange"
    assert body["subject_token"] == "user_jwt"
    assert body["actor_token"] == "actor_jwt"
    assert body["subject_token_profile"] == DEFAULT_PROFILE_NAME
    assert body["scope"] == "read:mcp:data write:mcp:data"


def test_token_exchange_error_raised_on_4xx() -> None:
    def fake_post(self, url, *, data, headers, **kwargs):  # noqa: ARG001
        return httpx.Response(
            status_code=400,
            request=httpx.Request("POST", url),
            json={"error": "invalid_grant", "error_description": "bad subject token"},
        )

    broker = TokenExchangeBroker(http_client=httpx.Client())
    with patch.object(httpx.Client, "post", fake_post), patch(
        "aqp.auth.token_exchange.settings", _settings_with()
    ):
        with pytest.raises(TokenExchangeError) as exc_info:
            broker.mint_for_agent(
                user_access_token="user_jwt",
                agent_actor_token="actor_jwt",
                agent_subject="agent|x",
                user_subject="auth0|y",
            )
    assert exc_info.value.code == "invalid_grant"
    assert "bad subject token" in str(exc_info.value)


def test_invalidate_drops_cached_entries() -> None:
    broker = TokenExchangeBroker()
    fake_token = DelegatedToken(
        access_token="abc",
        expires_at=time.time() + 300,
        scope="read:mcp:data",
        audience="https://api.example/",
        act_sub="agent|x",
        on_behalf_of_sub="auth0|user1",
        raw_response={},
    )
    from aqp.auth.token_exchange import _CacheKey

    key = _CacheKey(
        user_sub="auth0|user1",
        agent_sub="agent|x",
        audience="https://api.example/",
        scope_sorted=("read:mcp:data",),
        profile=DEFAULT_PROFILE_NAME,
    )
    broker._cache[key] = fake_token  # type: ignore[attr-defined]
    assert broker.invalidate(user_subject="auth0|user1") == 1
    assert broker.invalidate(user_subject="auth0|user1") == 0


def test_cached_tokens_returned_within_skew_window() -> None:
    broker = TokenExchangeBroker()
    fake_token = DelegatedToken(
        access_token="cached.jwt",
        expires_at=time.time() + 300,
        scope="read:mcp:data",
        audience="https://api.example/",
        act_sub="agent|x",
        on_behalf_of_sub="auth0|user1",
        raw_response={},
    )
    from aqp.auth.token_exchange import _CacheKey

    key = _CacheKey(
        user_sub="auth0|user1",
        agent_sub="agent|x",
        audience="https://api.example/",
        scope_sorted=tuple(sorted(DEFAULT_AGENT_SCOPES)),
        profile=DEFAULT_PROFILE_NAME,
    )
    broker._cache[key] = fake_token  # type: ignore[attr-defined]
    with patch("aqp.auth.token_exchange.settings", _settings_with()):
        result = broker.mint_for_agent(
            user_access_token="user_jwt",
            agent_actor_token="actor_jwt",
            agent_subject="agent|x",
            user_subject="auth0|user1",
            audience="https://api.example/",
        )
    assert result is fake_token
