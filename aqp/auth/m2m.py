"""Service-to-service token issuer.

The :class:`M2MTokenIssuer` mints short-lived bearer tokens via the
active :class:`aqp.auth.providers.IdentityProvider`'s
``client_credentials`` grant and caches them per
``(audience, scope)`` until expiry.

Wires into :mod:`aqp.credentials` via :class:`M2MStore`, which plugs
in front of :class:`FileSecretStore` (priority 10 vs 50) so any service
whose credential key is registered with the issuer transparently gets a
fresh M2M token instead of the bootstrap-minted file payload.

Disabled by default — enable with ``AQP_AUTH_M2M_ENABLED=true`` (see
``settings.auth_m2m_enabled``). When disabled, the issuer is not added
to the resolver chain and services keep using the file/env path.

The issuer is best-effort: if the IdP rejects a request or is
unreachable, the corresponding :meth:`SecretStore.get` returns ``None``
so the resolver falls through to the file/env stores. Callers see no
behavior change beyond a log line.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from aqp.auth.providers import (
    IdentityProvider,
    IdentityProviderError,
    M2MTokenResult,
    get_active_provider,
)
from aqp.credentials.protocol import (
    PRIORITY_M2M,
    Credential,
    CredentialKey,
    SecretStore,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audience map
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class M2MAudienceSpec:
    """Per-(service, purpose) M2M parameters."""

    audience: str
    scope: str | None = None


# Default audiences AQP recognises. Operators override via settings:
# ``AQP_AUTH_M2M_AUDIENCE`` is the global fallback when a key has no
# entry below; per-service overrides happen by adding rows here.
_DEFAULT_M2M_MAP: dict[tuple[str, str], M2MAudienceSpec] = {
    ("polaris", "oauth"): M2MAudienceSpec(audience="aqp:polaris", scope="catalog:write"),
    ("polaris", "rest"): M2MAudienceSpec(audience="aqp:polaris", scope="catalog:write"),
    ("trino", "basic"): M2MAudienceSpec(audience="aqp:trino", scope="trino:read"),
    ("minio", "sts"): M2MAudienceSpec(audience="aqp:minio", scope="s3:assume"),
    ("iceberg", "rest"): M2MAudienceSpec(audience="aqp:polaris", scope="catalog:write"),
}


# ---------------------------------------------------------------------------
# Issuer
# ---------------------------------------------------------------------------


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float
    scope: str | None


class M2MTokenIssuer:
    """Mint short-lived service tokens via the active provider."""

    def __init__(
        self,
        *,
        provider: IdentityProvider | None = None,
        default_ttl_seconds: int = 900,
        cache_skew_seconds: int = 30,
    ) -> None:
        self._provider = provider
        self._default_ttl = max(60, int(default_ttl_seconds))
        self._skew = max(0, int(cache_skew_seconds))
        self._cache: dict[tuple[str, str | None], _CachedToken] = {}
        self._lock = threading.RLock()

    def _provider_handle(self) -> IdentityProvider:
        return self._provider or get_active_provider()

    def token_for(
        self,
        service: str,
        *,
        purpose: str = "default",
        audience: str | None = None,
        scope: str | None = None,
    ) -> M2MTokenResult | None:
        """Return a fresh M2M token for ``(service, purpose)``.

        Returns ``None`` instead of raising on provider/IdP failures so
        the credential resolver can fall through to file/env. Callers
        that want to fail loudly should check the return for ``None``.
        """
        spec = _DEFAULT_M2M_MAP.get((service.lower(), purpose.lower()))
        eff_audience = audience or (spec.audience if spec else None) or _global_audience_fallback()
        eff_scope = scope or (spec.scope if spec else None) or _global_scope_fallback()
        if not eff_audience:
            logger.debug("M2MTokenIssuer: no audience for %s:%s; skipping", service, purpose)
            return None

        cache_key = (eff_audience, eff_scope)
        now = time.time()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None and now + self._skew < cached.expires_at:
                return M2MTokenResult(
                    access_token=cached.access_token,
                    expires_in=max(1, int(cached.expires_at - now)),
                    scope=cached.scope,
                )

        try:
            token = self._provider_handle().m2m_token(audience=eff_audience, scope=eff_scope)
        except IdentityProviderError as exc:
            logger.warning("M2MTokenIssuer: provider rejected %s:%s (%s)", service, purpose, exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("M2MTokenIssuer: unexpected failure for %s:%s (%s)", service, purpose, exc)
            return None

        ttl = int(token.expires_in or self._default_ttl)
        with self._lock:
            self._cache[cache_key] = _CachedToken(
                access_token=token.access_token,
                expires_at=now + max(60, ttl),
                scope=token.scope or eff_scope,
            )
        return token

    def reset(self) -> None:
        """Drop the token cache (used by tests + rotation runbooks)."""
        with self._lock:
            self._cache.clear()


# ---------------------------------------------------------------------------
# CredentialResolver adapter
# ---------------------------------------------------------------------------


class M2MStore(SecretStore):
    """Resolves :class:`CredentialKey` to a fresh M2M-minted bearer.

    The resolver merges this with the env-store payload (which carries
    the static client_id / endpoint / audience). Subscribed services
    map an M2M token onto their existing credential field name so no
    consumer has to learn about M2M tokens directly:

    - ``polaris:oauth`` → ``{"access_token": <m2m>, "principal": "<m2m>"}``
    - ``trino:basic`` → ``{"token": <m2m>}``
    - ``minio:sts`` → ``{"session_token": <m2m>}``

    The resolver caller still gets the static ``client_id`` /
    ``endpoint_url`` / ``audience`` fields it always got — those come
    from the env store via ``Credential.merge_default``.
    """

    store_kind = "m2m"
    store_alias = "M2MStore"
    store_priority = PRIORITY_M2M

    def __init__(self, issuer: M2MTokenIssuer | None = None) -> None:
        self._issuer = issuer or M2MTokenIssuer()

    def get(self, key: CredentialKey) -> Credential | None:
        if not _m2m_enabled():
            return None
        token = self._issuer.token_for(key.service, purpose=key.purpose)
        if token is None or not token.access_token:
            return None
        ttl = max(60, int(token.expires_in or 900))
        if key.service == "minio":
            return Credential(
                fields={"session_token": token.access_token},
                source=self.store_kind,
                ttl_seconds=ttl,
            )
        # Default M2M payload: surface as both ``access_token`` and
        # ``token`` so consumers using either name pick it up.
        return Credential(
            fields={"access_token": token.access_token, "token": token.access_token},
            source=self.store_kind,
            ttl_seconds=ttl,
        )


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def _m2m_enabled() -> bool:
    try:
        from aqp.config import settings

        return bool(getattr(settings, "auth_m2m_enabled", False))
    except Exception:
        return False


def _global_audience_fallback() -> str:
    try:
        from aqp.config import settings

        return str(getattr(settings, "auth_m2m_audience", "") or "")
    except Exception:
        return ""


def _global_scope_fallback() -> str | None:
    try:
        from aqp.config import settings

        scope = str(getattr(settings, "auth_m2m_scope", "") or "")
        return scope or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public install hook
# ---------------------------------------------------------------------------


def install_m2m_store(issuer: M2MTokenIssuer | None = None) -> M2MStore | None:
    """Install :class:`M2MStore` on the singleton resolver if enabled.

    Returns the installed store (or ``None`` when M2M is disabled).
    Idempotent: call from API + worker startup without thinking about
    duplicates; the resolver de-duplicates by class.
    """
    if not _m2m_enabled():
        return None
    from aqp.credentials import register_store

    store = M2MStore(issuer=issuer)
    register_store(store)
    logger.info("M2M token issuer installed on credential resolver")
    return store


__all__ = [
    "M2MAudienceSpec",
    "M2MStore",
    "M2MTokenIssuer",
    "install_m2m_store",
]
