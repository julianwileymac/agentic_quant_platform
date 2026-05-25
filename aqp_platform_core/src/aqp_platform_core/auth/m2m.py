"""M2M token broker — Entra-primary, Auth0 fallback.

The broker mints + caches a service-to-service bearer token that the
admin BFF uses to call the control plane, and the control plane uses
to push audit rows back to the monolith. Honours the canonical
:class:`aqp_platform_core.credentials.SecretStore` chain (rule 26)
so secret rotation is a non-event.

The default IdP is :func:`default_identity_provider_alias`
(Entra-primary post the rule-27 + identity.mdc update). Auth0 stays
available as a fallback for legacy + B2C deployments — instantiate a
:class:`M2MTokenBroker` with ``provider_alias='auth0'`` to opt in.

Caching strategy: per-(audience, scopes) entry, refreshed when the
remaining lifetime drops below ``refresh_skew_seconds`` (default 60s)
or on demand via :meth:`invalidate`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Iterable

from aqp_platform_core.auth.providers.msal_entra import MsalEntraValidator
from aqp_platform_core.auth.providers.protocol import (
    IdentityProviderShim,
    M2MGrant,
)
from aqp_platform_core.credentials.protocol import (
    Credential,
    CredentialKey,
    SecretStore,
)

# Inlined env-var read so this module is import-safe before
# ``aqp_platform_core.auth.__init__`` finishes loading. Mirrors the
# ``default_identity_provider_alias`` helper but without the
# circular import.
_ENTRA_ALIASES_FOR_BROKER: frozenset[str] = frozenset({
    "msal_entra", "entra", "msal", "azure_ad",
})


def _resolve_default_provider_alias() -> str:
    raw = (
        os.environ.get("AQP_AUTH_PROVIDER")
        or os.environ.get("AQP_CP_AUTH_PROVIDER")
        or "msal_entra"
    )
    alias = raw.strip().lower() or "msal_entra"
    if alias in _ENTRA_ALIASES_FOR_BROKER:
        return "msal_entra"
    return alias

logger = logging.getLogger(__name__)


class M2MBrokerError(RuntimeError):
    """Raised when the broker cannot mint or refresh a token."""

    def __init__(self, message: str, *, code: str = "m2m_broker_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class M2MTokenBrokerConfig:
    """Static configuration for the broker."""

    provider_alias: str
    tenant: str
    credential_key: CredentialKey
    refresh_skew_seconds: int = 60
    request_timeout_seconds: float = 10.0


@dataclass(slots=True)
class _CachedGrant:
    grant: M2MGrant
    cache_key: tuple[str, tuple[str, ...]]


class M2MTokenBroker:
    """Mint + cache machine-to-machine bearer tokens for boundary calls.

    Construct one broker per ``(provider, credential_key)`` pair —
    typically one for ``aqp-admin -> aqp-control-plane`` and one for
    ``aqp-control-plane -> aqp-monolith``.
    """

    def __init__(
        self,
        config: M2MTokenBrokerConfig,
        *,
        secret_stores: Iterable[SecretStore],
        provider: IdentityProviderShim | None = None,
    ) -> None:
        self._config = config
        self._secret_stores: tuple[SecretStore, ...] = tuple(
            sorted(secret_stores, key=lambda s: int(getattr(s, "store_priority", 100)))
        )
        self._provider: IdentityProviderShim = provider or self._build_provider()
        self._cache: dict[tuple[str, tuple[str, ...]], _CachedGrant] = {}
        self._lock = asyncio.Lock()

    @property
    def provider_alias(self) -> str:
        return self._provider.provider_alias

    @property
    def config(self) -> M2MTokenBrokerConfig:
        return self._config

    async def acquire(
        self,
        *,
        audience: str,
        scopes: tuple[str, ...] = (),
    ) -> M2MGrant:
        """Return a cached M2M grant for ``(audience, scopes)``.

        Re-mints on cold-start, near-expiry, or explicit
        :meth:`invalidate`. Raises :class:`M2MBrokerError` when no
        credential is available or the IdP refuses the grant.
        """
        cache_key = (audience, scopes)
        cached = self._cache.get(cache_key)
        now = time.time()
        if cached is not None and cached.grant.expires_at - now > self._config.refresh_skew_seconds:
            return cached.grant
        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None and cached.grant.expires_at - time.time() > self._config.refresh_skew_seconds:
                return cached.grant
            grant = await self._mint(audience=audience, scopes=scopes)
            self._cache[cache_key] = _CachedGrant(grant=grant, cache_key=cache_key)
            return grant

    def invalidate(
        self,
        *,
        audience: str | None = None,
        scopes: tuple[str, ...] | None = None,
    ) -> None:
        """Drop cached grants. With no args, drops every entry."""
        if audience is None and scopes is None:
            self._cache.clear()
            return
        keys_to_drop = [
            key for key in list(self._cache.keys())
            if (audience is None or key[0] == audience)
            and (scopes is None or key[1] == scopes)
        ]
        for key in keys_to_drop:
            self._cache.pop(key, None)

    async def close(self) -> None:
        """Release the provider's underlying http client (if any)."""
        closer = getattr(self._provider, "close", None)
        if callable(closer):
            try:
                result = closer()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001
                logger.debug("provider close failed", exc_info=True)

    async def _mint(
        self,
        *,
        audience: str,
        scopes: tuple[str, ...],
    ) -> M2MGrant:
        credential = self._resolve_credential()
        client_id = credential.get("client_id") or credential.get("id")
        client_secret = credential.get("client_secret") or credential.get("secret")
        if not client_id or not client_secret:
            raise M2MBrokerError(
                f"credential {self._config.credential_key} missing client_id / client_secret fields "
                f"(source={credential.source})",
                code="m2m_credential_incomplete",
            )
        return await self._provider.acquire_m2m_grant(
            client_id=client_id,
            client_secret=client_secret,
            audience=audience,
            scopes=scopes,
        )

    def _resolve_credential(self) -> Credential:
        for store in self._secret_stores:
            try:
                value = store.get(self._config.credential_key)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "secret store %s raised resolving %s: %s",
                    store.__class__.__name__,
                    self._config.credential_key,
                    exc,
                )
                continue
            if value is not None:
                return value
        raise M2MBrokerError(
            f"no secret store could resolve {self._config.credential_key}",
            code="m2m_credential_missing",
        )

    def _build_provider(self) -> IdentityProviderShim:
        alias = self._config.provider_alias.strip().lower()
        if alias in ("", "msal_entra", "entra", "msal", "azure_ad"):
            return MsalEntraValidator(
                tenant=self._config.tenant,
                audience=self._config.credential_key.service,
                http_timeout_seconds=self._config.request_timeout_seconds,
            )
        raise M2MBrokerError(
            f"unsupported provider_alias {alias!r}; provide an explicit provider= argument",
            code="m2m_provider_unsupported",
        )


def broker_for_default_provider(
    *,
    credential_key: CredentialKey,
    tenant: str | None = None,
    secret_stores: Iterable[SecretStore],
    refresh_skew_seconds: int = 60,
    request_timeout_seconds: float = 10.0,
    provider: IdentityProviderShim | None = None,
) -> M2MTokenBroker:
    """Build an :class:`M2MTokenBroker` using the platform default IdP.

    Resolves the provider alias via
    :func:`default_identity_provider_alias` (Entra-primary after the
    rule-27 + identity.mdc update). The ``tenant`` argument defaults
    to ``organizations`` for Entra (B2B / B2C enterprise customers).
    """
    alias = _resolve_default_provider_alias()
    config = M2MTokenBrokerConfig(
        provider_alias=alias,
        tenant=tenant or "organizations",
        credential_key=credential_key,
        refresh_skew_seconds=refresh_skew_seconds,
        request_timeout_seconds=request_timeout_seconds,
    )
    return M2MTokenBroker(
        config,
        secret_stores=secret_stores,
        provider=provider,
    )


__all__ = [
    "M2MBrokerError",
    "M2MTokenBroker",
    "M2MTokenBrokerConfig",
    "broker_for_default_provider",
]
