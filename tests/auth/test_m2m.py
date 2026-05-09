"""Tests for :mod:`aqp.auth.m2m`."""
from __future__ import annotations

import pytest

from aqp.auth.m2m import (
    M2MStore,
    M2MTokenIssuer,
    install_m2m_store,
)
from aqp.auth.providers import (
    IdentityProvider,
    IdentityProviderConfig,
    IdentityProviderError,
    M2MTokenResult,
    register_provider,
    reset_active_provider,
)
from aqp.credentials import (
    CredentialKey,
    CredentialResolver,
    SecretStore,
    reset_resolver,
)


class _ScriptedProvider(IdentityProvider):
    """Provider that records calls and returns a scripted token."""

    provider_kind = "scripted-test"
    provider_alias = "ScriptedProvider"

    def __init__(
        self,
        token: M2MTokenResult | None = None,
        *,
        raise_with: Exception | None = None,
    ) -> None:
        super().__init__(
            IdentityProviderConfig(
                issuer="http://idp.test",
                audience="aqp-test",
                client_id="aqp",
                client_secret="x",
            )
        )
        self.calls: list[tuple[str | None, str | None]] = []
        self._token = token
        self._raise = raise_with

    def discovery(self):
        return {}

    def jwks(self):
        return {"keys": []}

    def login_url(self, **_):
        return ""

    def exchange_code(self, **_):
        from aqp.auth.providers.protocol import TokenResponse

        return TokenResponse(access_token="x")

    def refresh(self, refresh_token):
        from aqp.auth.providers.protocol import TokenResponse

        return TokenResponse(access_token=refresh_token)

    def logout_url(self, **_):
        return ""

    def m2m_token(self, *, audience=None, scope=None) -> M2MTokenResult:
        self.calls.append((audience, scope))
        if self._raise is not None:
            raise self._raise
        if self._token is not None:
            return self._token
        return M2MTokenResult(access_token=f"token-for-{audience}", expires_in=900, scope=scope)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    reset_resolver()
    reset_active_provider()
    yield
    reset_resolver()
    reset_active_provider()


def _enable_m2m(monkeypatch):
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "auth_m2m_enabled", True, raising=False)


def test_issuer_token_for_polaris_uses_default_audience(monkeypatch):
    _enable_m2m(monkeypatch)
    provider = _ScriptedProvider()
    register_provider(provider)
    issuer = M2MTokenIssuer(provider=provider)

    result = issuer.token_for("polaris", purpose="oauth")

    assert result is not None
    assert result.access_token == "token-for-aqp:polaris"
    assert provider.calls == [("aqp:polaris", "catalog:write")]


def test_issuer_caches_token_until_expiry(monkeypatch):
    _enable_m2m(monkeypatch)
    provider = _ScriptedProvider(
        token=M2MTokenResult(access_token="cached", expires_in=900, scope=None)
    )
    issuer = M2MTokenIssuer(provider=provider)

    issuer.token_for("polaris", purpose="oauth")
    issuer.token_for("polaris", purpose="oauth")

    assert len(provider.calls) == 1


def test_issuer_returns_none_on_provider_error(monkeypatch):
    _enable_m2m(monkeypatch)
    provider = _ScriptedProvider(raise_with=IdentityProviderError("nope"))
    issuer = M2MTokenIssuer(provider=provider)

    assert issuer.token_for("polaris", purpose="oauth") is None


def test_issuer_returns_none_when_no_audience_known(monkeypatch):
    """Unknown (service, purpose) + empty global audience = no token."""
    _enable_m2m(monkeypatch)
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "auth_m2m_audience", "", raising=False)
    provider = _ScriptedProvider()
    issuer = M2MTokenIssuer(provider=provider)

    assert issuer.token_for("nonexistent-service") is None
    assert provider.calls == []  # never reached the IdP


def test_m2m_store_returns_none_when_disabled(monkeypatch):
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "auth_m2m_enabled", False, raising=False)
    store = M2MStore()
    assert store.get(CredentialKey("polaris", "oauth")) is None


def test_m2m_store_resolves_polaris_token(monkeypatch):
    _enable_m2m(monkeypatch)
    provider = _ScriptedProvider()
    register_provider(provider)
    issuer = M2MTokenIssuer(provider=provider)
    store = M2MStore(issuer=issuer)

    cred = store.get(CredentialKey("polaris", "oauth"))

    assert cred is not None
    assert cred.source == "m2m"
    assert cred.get("access_token") == "token-for-aqp:polaris"
    assert cred.get("token") == "token-for-aqp:polaris"


def test_m2m_store_minio_uses_session_token_field(monkeypatch):
    _enable_m2m(monkeypatch)
    provider = _ScriptedProvider()
    register_provider(provider)
    issuer = M2MTokenIssuer(provider=provider)
    store = M2MStore(issuer=issuer)

    cred = store.get(CredentialKey("minio", "sts"))

    assert cred is not None
    assert cred.get("session_token") == "token-for-aqp:minio"


def test_install_m2m_noop_when_disabled(monkeypatch):
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "auth_m2m_enabled", False, raising=False)
    assert install_m2m_store() is None


def test_install_m2m_adds_store_to_resolver(monkeypatch):
    _enable_m2m(monkeypatch)
    provider = _ScriptedProvider()
    register_provider(provider)

    store = install_m2m_store()
    assert store is not None

    # The resolver singleton picked the store up; M2M should now win
    # over file/env even with no bootstrap file present.
    from aqp.credentials import get_resolver

    cred = get_resolver().resolve(CredentialKey("polaris", "oauth"))
    assert cred.source == "m2m"


def test_resolver_chain_prioritises_m2m_over_file(monkeypatch, tmp_path):
    _enable_m2m(monkeypatch)
    (tmp_path / "polaris-principal.json").write_text(
        '{"client_id": "file-id", "client_secret": "file-secret"}'
    )
    from aqp.credentials.stores.file_store import FileSecretStore

    provider = _ScriptedProvider()
    issuer = M2MTokenIssuer(provider=provider)
    resolver = CredentialResolver(
        [
            FileSecretStore(base_dir=tmp_path),
            M2MStore(issuer=issuer),
        ]
    )
    cred = resolver.resolve(CredentialKey("polaris", "oauth"))
    assert cred.source == "m2m"
