"""Tests for :mod:`aqp.auth.providers`.

Covers the Auth0 / generic OIDC / mock providers and the active-provider
selection logic. The OIDC HTTP client is exercised by the mock provider
(deterministic) and through monkey-patched ``httpx`` calls for the
discovery / token-exchange flows.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

from aqp.auth.providers import (
    Auth0Provider,
    GenericOidcProvider,
    IdentityProvider,
    IdentityProviderConfig,
    MockProvider,
    get_active_provider,
    list_provider_classes,
    register_provider,
    reset_active_provider,
)
from aqp.auth.providers.protocol import IDENTITY_PROVIDER_KIND


@pytest.fixture(autouse=True)
def _reset_provider():
    reset_active_provider()
    yield
    reset_active_provider()


def test_metaclass_registers_concrete_providers():
    classes = list_provider_classes()
    aliases = set(classes.keys())
    assert "Auth0Provider" in aliases
    assert "GenericOidcProvider" in aliases
    assert "MockProvider" in aliases


def test_metaclass_skips_abstract_base():
    classes = list_provider_classes()
    # IdentityProvider itself is abstract and must not appear in the
    # registry under its own name.
    assert "IdentityProvider" not in classes


def test_kind_index_uses_identity_provider_label():
    from aqp.core.registry import list_by_kind

    classes = list_by_kind(IDENTITY_PROVIDER_KIND)
    assert "Auth0Provider" in classes
    assert "MockProvider" in classes


def test_mock_provider_login_url_includes_pkce_params():
    provider = MockProvider()
    url = provider.login_url(
        redirect_uri="http://localhost:8000/auth/callback",
        state="state-123",
        code_challenge="challenge-abc",
        scope="openid email",
        audience="aqp-api",
    )
    parsed = parse_qs(urlparse(url).query)
    assert parsed["state"] == ["state-123"]
    assert parsed["code_challenge"] == ["challenge-abc"]
    assert parsed["code_challenge_method"] == ["S256"]
    assert parsed["audience"] == ["aqp-api"]
    assert parsed["scope"] == ["openid email"]


def test_mock_provider_exchange_code_returns_synthetic_tokens():
    provider = MockProvider()
    tokens = provider.exchange_code(
        code="abc",
        redirect_uri="http://localhost/cb",
        code_verifier="verifier-1234567890123456789012345678901234567890",
    )
    assert tokens.access_token.startswith("mock-access-")
    assert tokens.id_token is not None and tokens.id_token.startswith("mock-id-")
    assert tokens.refresh_token is not None and tokens.refresh_token.startswith("mock-refresh-")
    assert tokens.expires_in == 3600


def test_mock_provider_m2m_token_round_trips():
    provider = MockProvider()
    token = provider.m2m_token(audience="aqp-services", scope="polaris:write")
    assert token.access_token.startswith("mock-m2m-")
    assert token.expires_in == 900
    assert token.scope == "polaris:write"


def test_mock_provider_logout_url_includes_return_to():
    provider = MockProvider()
    url = provider.logout_url(return_to="http://localhost/done")
    parsed = parse_qs(urlparse(url).query)
    assert parsed["post_logout_redirect_uri"] == ["http://localhost/done"]


def test_auth0_logout_url_uses_v2_logout():
    provider = Auth0Provider(
        IdentityProviderConfig(
            issuer="https://tenant.auth0.com",
            audience="aqp-api",
            client_id="aqp-spa",
        )
    )
    url = provider.logout_url(return_to="http://localhost/done")
    parsed = urlparse(url)
    assert parsed.netloc == "tenant.auth0.com"
    assert parsed.path == "/v2/logout"
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["aqp-spa"]
    assert qs["returnTo"] == ["http://localhost/done"]


def test_auth0_logout_url_falls_back_to_configured_callback():
    provider = Auth0Provider(
        IdentityProviderConfig(
            issuer="https://tenant.auth0.com",
            audience="aqp-api",
            client_id="aqp-spa",
            logout_callback="http://localhost/callback-default",
        )
    )
    url = provider.logout_url()
    qs = parse_qs(urlparse(url).query)
    assert qs["returnTo"] == ["http://localhost/callback-default"]


def test_generic_oidc_logout_url_uses_end_session_endpoint():
    provider = GenericOidcProvider(
        IdentityProviderConfig(
            issuer="https://idp.example.com/realms/aqp",
            audience="aqp-api",
            client_id="aqp-client",
        )
    )

    discovery = {
        "issuer": "https://idp.example.com/realms/aqp",
        "end_session_endpoint": "https://idp.example.com/realms/aqp/protocol/openid-connect/logout",
        "authorization_endpoint": "https://idp.example.com/realms/aqp/protocol/openid-connect/auth",
        "token_endpoint": "https://idp.example.com/realms/aqp/protocol/openid-connect/token",
        "jwks_uri": "https://idp.example.com/realms/aqp/protocol/openid-connect/certs",
    }
    with patch.object(provider, "discovery", return_value=discovery):
        url = provider.logout_url(return_to="http://localhost/done", id_token_hint="hint")

    parsed = urlparse(url)
    assert parsed.netloc == "idp.example.com"
    assert parsed.path == "/realms/aqp/protocol/openid-connect/logout"
    qs = parse_qs(parsed.query)
    assert qs["post_logout_redirect_uri"] == ["http://localhost/done"]
    assert qs["id_token_hint"] == ["hint"]


def test_generic_oidc_login_url_attaches_pkce_and_audience():
    provider = GenericOidcProvider(
        IdentityProviderConfig(
            issuer="https://idp.example.com/realms/aqp",
            audience="aqp-api",
            client_id="aqp-client",
        )
    )
    discovery = {
        "authorization_endpoint": "https://idp.example.com/realms/aqp/protocol/openid-connect/auth",
        "token_endpoint": "https://idp.example.com/realms/aqp/protocol/openid-connect/token",
        "jwks_uri": "https://idp.example.com/realms/aqp/protocol/openid-connect/certs",
    }
    with patch("aqp.auth.oidc_client.OidcHttpClient.discovery", return_value=discovery):
        url = provider.login_url(
            redirect_uri="http://localhost/cb",
            state="s",
            code_challenge="c",
            scope="openid email",
        )
    qs = parse_qs(urlparse(url).query)
    assert qs["client_id"] == ["aqp-client"]
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["audience"] == ["aqp-api"]


def test_register_provider_overrides_active(monkeypatch):
    class _Spy(IdentityProvider):
        provider_kind = "spy-test"
        provider_alias = "SpyProvider"

        def discovery(self) -> dict[str, Any]:
            return {}

        def jwks(self) -> dict[str, Any]:
            return {"keys": []}

        def login_url(self, **_):
            return "http://spy/login"

        def exchange_code(self, **_):
            from aqp.auth.providers.protocol import TokenResponse

            return TokenResponse(access_token="spy")

        def refresh(self, refresh_token: str):
            from aqp.auth.providers.protocol import TokenResponse

            return TokenResponse(access_token="spy")

        def logout_url(self, **_):
            return "http://spy/logout"

        def m2m_token(self, **_):
            from aqp.auth.providers.protocol import M2MTokenResult

            return M2MTokenResult(access_token="spy", expires_in=60)

    spy = _Spy(
        IdentityProviderConfig(
            issuer="http://spy", audience="spy-api", client_id="spy", client_secret="x"
        )
    )
    register_provider(spy)
    assert get_active_provider() is spy


def test_get_active_provider_falls_back_to_mock(monkeypatch):
    """When ``auth_provider`` is unknown, the resolver picks the mock."""
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "auth_provider", "definitely-not-a-real-provider", raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_issuer", "http://mock-idp.local", raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_audience", "aqp-mock", raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_client_id", "aqp-mock-client", raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_client_secret", "aqp-mock-secret", raising=False)
    monkeypatch.setattr(_settings, "auth_logout_callback", "", raising=False)

    provider = get_active_provider()
    assert isinstance(provider, MockProvider)


def test_get_active_provider_selects_auth0(monkeypatch):
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "auth_provider", "auth0", raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_issuer", "https://tenant.auth0.com", raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_audience", "aqp-api", raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_client_id", "aqp-spa", raising=False)
    monkeypatch.setattr(_settings, "auth_oidc_client_secret", "secret", raising=False)
    monkeypatch.setattr(_settings, "auth_logout_callback", "", raising=False)

    provider = get_active_provider()
    assert isinstance(provider, Auth0Provider)


def test_describe_returns_safe_metadata():
    provider = MockProvider()
    info = provider.describe()
    assert info["kind"] == "mock"
    assert info["alias"] == "MockProvider"
    assert "client_secret" not in info
