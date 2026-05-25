"""M2M token broker tests — credential resolution + cache + refresh."""
from __future__ import annotations

import time

import pytest

from aqp_platform_core.auth.m2m import (
    M2MBrokerError,
    M2MTokenBroker,
    M2MTokenBrokerConfig,
)
from aqp_platform_core.auth.providers.protocol import M2MGrant
from aqp_platform_core.credentials.protocol import (
    Credential,
    CredentialKey,
    SecretStore,
)


class _InMemoryStore(SecretStore):
    store_kind = "memory"
    store_priority = 50

    def __init__(self, fields: dict[str, str]) -> None:
        self._fields = fields

    def get(self, key: CredentialKey) -> Credential | None:  # noqa: ARG002
        return Credential(fields=self._fields, source=self.store_kind)


class _StubProvider:
    provider_alias = "stub"

    def __init__(self, *, expires_in: int = 3600) -> None:
        self.calls: list[tuple[str, str, str, tuple[str, ...]]] = []
        self._expires_in = expires_in

    @property
    def config(self):  # type: ignore[override]
        return None

    def jwt_validator(self):  # type: ignore[override]
        raise NotImplementedError

    def token_endpoint(self) -> str:
        return "https://stub/token"

    async def acquire_m2m_grant(
        self,
        *,
        client_id: str,
        client_secret: str,
        audience: str,
        scopes: tuple[str, ...] = (),
        extra=None,
    ) -> M2MGrant:
        self.calls.append((client_id, client_secret, audience, scopes))
        now = time.time()
        return M2MGrant(
            access_token=f"token-{len(self.calls)}",
            expires_at=now + self._expires_in,
            issued_at=now,
            scope=scopes,
        )


@pytest.mark.asyncio
async def test_broker_mints_and_caches() -> None:
    store = _InMemoryStore({"client_id": "cid", "client_secret": "sec"})
    provider = _StubProvider()
    broker = M2MTokenBroker(
        M2MTokenBrokerConfig(
            provider_alias="stub",
            tenant="organizations",
            credential_key=CredentialKey(service="aqp-admin-to-cp", purpose="cc"),
        ),
        secret_stores=(store,),
        provider=provider,
    )
    grant1 = await broker.acquire(audience="api://cp", scopes=("read",))
    grant2 = await broker.acquire(audience="api://cp", scopes=("read",))
    assert grant1.access_token == grant2.access_token
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_broker_refreshes_after_invalidate() -> None:
    store = _InMemoryStore({"client_id": "cid", "client_secret": "sec"})
    provider = _StubProvider()
    broker = M2MTokenBroker(
        M2MTokenBrokerConfig(
            provider_alias="stub",
            tenant="organizations",
            credential_key=CredentialKey(service="aqp-admin-to-cp", purpose="cc"),
        ),
        secret_stores=(store,),
        provider=provider,
    )
    await broker.acquire(audience="api://cp")
    broker.invalidate(audience="api://cp", scopes=())
    await broker.acquire(audience="api://cp")
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_broker_raises_on_missing_credential() -> None:
    broker = M2MTokenBroker(
        M2MTokenBrokerConfig(
            provider_alias="stub",
            tenant="organizations",
            credential_key=CredentialKey(service="absent", purpose="cc"),
        ),
        secret_stores=(),
        provider=_StubProvider(),
    )
    with pytest.raises(M2MBrokerError):
        await broker.acquire(audience="api://cp")


@pytest.mark.asyncio
async def test_broker_raises_on_incomplete_credential() -> None:
    store = _InMemoryStore({"client_id": "cid"})  # missing secret
    broker = M2MTokenBroker(
        M2MTokenBrokerConfig(
            provider_alias="stub",
            tenant="organizations",
            credential_key=CredentialKey(service="aqp", purpose="cc"),
        ),
        secret_stores=(store,),
        provider=_StubProvider(),
    )
    with pytest.raises(M2MBrokerError):
        await broker.acquire(audience="api://cp")
