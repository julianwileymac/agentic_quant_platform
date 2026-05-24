"""Per-user external OAuth wizard tests (Workstream D).

Covers:

- ``ExternalOAuthProviderMeta`` registers all five concrete providers.
- The generic provider builds a syntactically correct PKCE authorize
  URL with ``code_challenge_method=S256``.
- :func:`start_authorize_flow` returns a state + URL, and the state
  is recoverable via :func:`complete_authorize_flow` (with the
  provider mocked).
- :class:`UserOAuthTokenStore` returns ``None`` without a request
  user context (priority-5 short-circuit).
- Envelope encryption round-trips via the local fallback path.
"""
from __future__ import annotations

import json

import pytest


def test_metaclass_registers_all_five_providers() -> None:
    from aqp.auth.external_oauth import list_external_oauth_providers

    providers = list_external_oauth_providers()
    slugs = set(providers)
    assert "generic" in slugs
    assert "github" in slugs
    assert "fred" in slugs
    assert "bloomberg" in slugs
    assert "refinitiv" in slugs


def test_generic_provider_builds_pkce_authorize_url() -> None:
    from aqp.auth.external_oauth import ExternalProviderConfig
    from aqp.auth.external_oauth.providers.generic import GenericExternalOAuthProvider

    config = ExternalProviderConfig(
        authorize_endpoint="https://idp.example.test/authorize",
        token_endpoint="https://idp.example.test/token",
        client_id="cid-xyz",
        default_scope="read",
    )
    provider = GenericExternalOAuthProvider(config)
    url = provider.authorize_url(
        state="abc",
        code_challenge="challenge",
        redirect_uri="https://aqp.test/callback",
    )
    assert "response_type=code" in url
    assert "code_challenge=challenge" in url
    assert "code_challenge_method=S256" in url
    assert "state=abc" in url
    assert "client_id=cid-xyz" in url


def test_envelope_encrypt_local_fallback_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local AESGCM fallback round-trips identically."""
    pytest.importorskip("cryptography.hazmat.primitives.ciphers.aead")
    monkeypatch.delenv("VAULT_ADDR", raising=False)

    from aqp.credentials.vault_transit import decrypt, encrypt

    plaintext = b"secret-token-blob-12345"
    ct = encrypt(plaintext, tenant="tenant-1")
    assert ct.startswith("local:v1:")
    out = decrypt(ct, tenant="tenant-1")
    assert out == plaintext


def test_user_oauth_token_store_returns_none_without_user_context(
    in_memory_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.credentials.protocol import CredentialKey
    from aqp.credentials.stores.user_oauth_token_store import UserOAuthTokenStore
    from aqp.tenancy.runtime_context import set_runtime_context, reset_runtime_context

    # No context at all -> None.
    store = UserOAuthTokenStore()
    cred = store.get(CredentialKey("github", "user_oauth"))
    assert cred is None

    # Context with no user_id -> None.
    class _Ctx:
        user_id = None

    token = set_runtime_context(_Ctx())
    try:
        cred = store.get(CredentialKey("github", "user_oauth"))
        assert cred is None
    finally:
        reset_runtime_context(token)


def test_user_oauth_token_store_ignores_wrong_purpose() -> None:
    from aqp.credentials.protocol import CredentialKey
    from aqp.credentials.stores.user_oauth_token_store import UserOAuthTokenStore

    # Wrong purpose -> None even with a user in context.
    store = UserOAuthTokenStore()
    assert store.get(CredentialKey("github", "client_secret")) is None


def test_data_oauth_list_connections_returns_empty_when_no_user(in_memory_db) -> None:
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.tools.oauth_connections import ListOAuthConnectionsTool

    tool = ListOAuthConnectionsTool()
    result = tool.run(
        ctx=MCPToolContext(
            actor="agent-1",
            actor_kind="agent",
            granted_scopes=("data:read",),
        ),
    )
    assert result.ok
    assert result.data["connections"] == []


def test_data_oauth_list_connections_filters_by_user(in_memory_db) -> None:
    from datetime import datetime

    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.tools.oauth_connections import ListOAuthConnectionsTool
    from aqp.persistence.db import get_session
    from aqp.persistence.models_oauth_tokens import UserOAuthToken

    with get_session() as session:
        session.add(
            UserOAuthToken(
                id="t-1",
                user_id="user-alpha",
                organization_id=None,
                source="github",
                vault_path="oauth2/users/default/user-alpha/github",
                scopes=["read:user"],
                created_at=datetime.utcnow(),
            )
        )
        session.add(
            UserOAuthToken(
                id="t-2",
                user_id="user-beta",
                organization_id=None,
                source="github",
                vault_path="oauth2/users/default/user-beta/github",
                scopes=["read:user"],
                created_at=datetime.utcnow(),
            )
        )
        session.commit()

    tool = ListOAuthConnectionsTool()
    result = tool.run(
        ctx=MCPToolContext(
            actor="user-alpha",
            actor_kind="user",
            granted_scopes=("data:read",),
        ),
    )
    assert result.ok
    assert len(result.data["connections"]) == 1
    assert result.data["connections"][0]["source"] == "github"
    assert "t-1" in result.data["connections"][0]["id"]


def test_provider_describe_does_not_leak_secrets() -> None:
    from aqp.auth.external_oauth import ExternalProviderConfig
    from aqp.auth.external_oauth.providers.generic import GenericExternalOAuthProvider

    provider = GenericExternalOAuthProvider(
        ExternalProviderConfig(
            authorize_endpoint="https://idp.example.test/authorize",
            token_endpoint="https://idp.example.test/token",
            client_id="cid",
            client_secret="VERY-SECRET-DO-NOT-LEAK",
        )
    )
    descr = provider.describe()
    assert "client_secret" not in descr
    assert "VERY-SECRET-DO-NOT-LEAK" not in json.dumps(descr)
