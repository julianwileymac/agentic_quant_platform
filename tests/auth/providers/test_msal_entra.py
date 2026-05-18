"""Tests for :class:`aqp.auth.providers.msal_entra.MsalEntraProvider`.

The msal package is optional — when missing the provider's
:meth:`_get_app` raises ``IdentityProviderError`` so we can skip the
tests that require msal directly. Discovery + JWKS + flow-store
tests work without msal because they don't construct the MSAL client.
"""
from __future__ import annotations

import importlib.util
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aqp.auth.providers import (
    IdentityProvider,
    IdentityProviderConfig,
    list_provider_classes,
)
from aqp.auth.providers.protocol import IDENTITY_PROVIDER_KIND


MSAL_AVAILABLE = importlib.util.find_spec("msal") is not None
requires_msal = pytest.mark.skipif(
    not MSAL_AVAILABLE, reason="msal not installed (pip install msal)"
)


def test_msal_provider_auto_registered():
    """Metaclass auto-registers MsalEntraProvider on import."""
    from aqp.auth.providers import msal_entra  # noqa: F401  - ensures import

    classes = list_provider_classes()
    assert "MsalEntraProvider" in classes
    cls = classes["MsalEntraProvider"]
    assert issubclass(cls, IdentityProvider)
    assert cls.provider_kind == "msal_entra"


def test_msal_provider_default_authority():
    """When config.issuer is empty the provider falls back to /organizations."""
    from aqp.auth.providers.msal_entra import MsalEntraProvider

    p = MsalEntraProvider(
        IdentityProviderConfig(issuer="", audience="api://test")
    )
    assert p._discovery_uri().endswith("/v2.0/.well-known/openid-configuration")
    assert "/organizations" in p._discovery_uri()


def test_msal_logout_url_strips_v2():
    """logout_url returns /oauth2/v2.0/logout regardless of the issuer suffix."""
    from aqp.auth.providers.msal_entra import MsalEntraProvider

    p = MsalEntraProvider(
        IdentityProviderConfig(
            issuer="https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000",
            audience="api://test",
        )
    )
    url = p.logout_url(return_to="https://app.example.com/done")
    assert "/oauth2/v2.0/logout" in url
    assert "post_logout_redirect_uri=" in url


def test_msal_flow_store_round_trip():
    """The in-process flow store survives a save -> pop with the matching state."""
    from aqp.auth.providers.msal_entra import _flow_store

    _flow_store.save("state-abc", {"auth_uri": "https://x", "code_verifier": "v"})
    flow = _flow_store.pop("state-abc")
    assert flow is not None
    assert flow["auth_uri"] == "https://x"
    # Second pop returns None (one-shot).
    assert _flow_store.pop("state-abc") is None


@requires_msal
def test_msal_login_url_stores_flow():
    """initiate_auth_code_flow result is stashed under the state key."""
    from aqp.auth.providers.msal_entra import MsalEntraProvider, _flow_store

    p = MsalEntraProvider(
        IdentityProviderConfig(
            issuer="https://login.microsoftonline.com/organizations",
            audience="api://aqp",
            client_id="00000000-0000-0000-0000-000000000001",
            client_secret="not-a-real-secret",
        )
    )
    # Stub MSAL's flow initiation so the test doesn't hit Microsoft.
    fake_flow = {
        "auth_uri": "https://login.microsoftonline.com/auth?state=state-xyz",
        "state": "state-xyz",
        "code_verifier": "verifier",
        "nonce": "nonce",
    }
    p._app = MagicMock()
    p._app.initiate_auth_code_flow.return_value = fake_flow

    url = p.login_url(
        redirect_uri="http://localhost:3001/auth/callback",
        state="state-xyz",
        code_challenge="ignored-by-msal",
    )
    assert url == fake_flow["auth_uri"]
    assert _flow_store.pop("state-xyz") == fake_flow


@requires_msal
def test_msal_exchange_code_requires_flow_state():
    """Without a stored flow the exchange raises IdentityProviderError."""
    from aqp.auth.providers.msal_entra import MsalEntraProvider
    from aqp.auth.providers.protocol import IdentityProviderError

    p = MsalEntraProvider(
        IdentityProviderConfig(
            issuer="https://login.microsoftonline.com/organizations",
            audience="api://aqp",
            client_id="00000000-0000-0000-0000-000000000001",
            client_secret="not-a-real-secret",
        )
    )
    p._app = MagicMock()
    with pytest.raises(IdentityProviderError) as exc_info:
        p.exchange_code(code="abc", redirect_uri="http://x", code_verifier="missing-state")
    assert "auth_code_flow" in str(exc_info.value)


@requires_msal
def test_msal_m2m_token_default_scope():
    """m2m_token derives ``.default`` scope from audience when scope is absent."""
    from aqp.auth.providers.msal_entra import MsalEntraProvider

    p = MsalEntraProvider(
        IdentityProviderConfig(
            issuer="https://login.microsoftonline.com/organizations",
            audience="api://aqp",
            client_id="00000000-0000-0000-0000-000000000001",
            client_secret="not-a-real-secret",
        )
    )
    p._app = MagicMock()
    p._app.acquire_token_for_client.return_value = {
        "access_token": "tok-123",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    result = p.m2m_token(audience="https://graph.microsoft.com")
    p._app.acquire_token_for_client.assert_called_once_with(
        scopes=["https://graph.microsoft.com/.default"]
    )
    assert result.access_token == "tok-123"
    assert result.expires_in == 3600
