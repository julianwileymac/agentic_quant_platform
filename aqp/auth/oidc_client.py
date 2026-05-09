"""Generic OIDC HTTP client — discovery, JWKS, token exchange, refresh, M2M.

Ported in spirit from
``inspiration/auth0-server-python-main/src/auth0_server_python/auth_server/server_client.py``
(MIT, Copyright Auth0, Inc.) but trimmed to the subset AQP needs:

- ``GET .well-known/openid-configuration`` (TTL-cached)
- ``GET <jwks_uri>`` (TTL-cached, serves stale on transient outage)
- ``POST <token_endpoint>`` for ``authorization_code`` (with PKCE)
- ``POST <token_endpoint>`` for ``refresh_token``
- ``POST <token_endpoint>`` for ``client_credentials``

This module purposefully does not know about Auth0 vs Keycloak vs
generic OIDC quirks — those belong to the
:class:`aqp.auth.providers.IdentityProvider` subclasses, which compose
this client and override anything provider-specific (logout URL, custom
audience handling, telemetry headers).

The discovery + JWKS caches are process-wide so all providers share
them, mirroring :mod:`aqp.auth.oidc`'s existing pattern.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OidcClientError(RuntimeError):
    """Generic OIDC HTTP failure."""


class TokenExchangeError(OidcClientError):
    """The token endpoint returned an error response."""


class DiscoveryUnavailableError(OidcClientError):
    """``.well-known/openid-configuration`` could not be fetched."""


# ---------------------------------------------------------------------------
# TTL caches
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    expires_at: float
    payload: dict[str, Any]


_DISCOVERY_CACHE: dict[str, _CacheEntry] = {}
_JWKS_CACHE: dict[str, _CacheEntry] = {}
_CACHE_LOCK = threading.RLock()

_DEFAULT_DISCOVERY_TTL_SECONDS = 600
_DEFAULT_JWKS_TTL_SECONDS = 3600


def reset_discovery_cache() -> None:
    """Drop both discovery and JWKS caches (used by tests + rotation runbooks)."""
    with _CACHE_LOCK:
        _DISCOVERY_CACHE.clear()
        _JWKS_CACHE.clear()


# ---------------------------------------------------------------------------
# OIDC HTTP client
# ---------------------------------------------------------------------------


class OidcHttpClient:
    """Stateless HTTP plumbing for OIDC providers.

    Construct one per provider; the provider keeps the instance for its
    lifetime so the underlying ``httpx.Client`` connection pool stays
    warm. Caches are module-level so they are shared across providers
    that point at the same issuer.
    """

    def __init__(
        self,
        *,
        discovery_url: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.discovery_url = (discovery_url or "").rstrip("/")
        self._timeout = float(timeout_seconds)
        self._client = client or httpx.Client(timeout=self._timeout)
        self._owns_client = client is None

    def __enter__(self) -> OidcHttpClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ------------------------------------------------------------------
    # Discovery + JWKS
    # ------------------------------------------------------------------

    def discovery(self, *, ttl: int = _DEFAULT_DISCOVERY_TTL_SECONDS) -> dict[str, Any]:
        if not self.discovery_url:
            raise DiscoveryUnavailableError("Empty discovery URL")
        url = self.discovery_url
        if not url.endswith("/.well-known/openid-configuration"):
            url = url.rstrip("/") + "/.well-known/openid-configuration"
        return self._fetch_cached(_DISCOVERY_CACHE, url, ttl=ttl)

    def jwks(self, *, ttl: int = _DEFAULT_JWKS_TTL_SECONDS) -> dict[str, Any]:
        meta = self.discovery()
        jwks_uri = str(meta.get("jwks_uri") or "").strip()
        if not jwks_uri:
            raise DiscoveryUnavailableError("Discovery document has no jwks_uri")
        return self._fetch_cached(_JWKS_CACHE, jwks_uri, ttl=ttl)

    def _fetch_cached(
        self,
        cache: dict[str, _CacheEntry],
        url: str,
        *,
        ttl: int,
    ) -> dict[str, Any]:
        now = time.time()
        with _CACHE_LOCK:
            cached = cache.get(url)
        if cached is not None and now < cached.expires_at:
            return cached.payload

        try:
            response = self._client.get(url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            if cached is not None:
                logger.warning(
                    "OIDC fetch %s failed (%s); serving cached payload past TTL",
                    url,
                    exc,
                )
                return cached.payload
            raise DiscoveryUnavailableError(f"GET {url} failed: {exc}") from exc

        if not isinstance(payload, dict):
            raise DiscoveryUnavailableError(f"GET {url} returned non-dict body")

        with _CACHE_LOCK:
            cache[url] = _CacheEntry(
                expires_at=now + max(60, int(ttl)),
                payload=payload,
            )
        return payload

    # ------------------------------------------------------------------
    # Token endpoint
    # ------------------------------------------------------------------

    def authorize_url(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        scope: str,
        audience: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        meta = self.discovery()
        endpoint = str(meta.get("authorization_endpoint") or "").strip()
        if not endpoint:
            raise OidcClientError("Discovery document has no authorization_endpoint")
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": scope,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if audience:
            params["audience"] = audience
        if extra_params:
            params.update({str(k): str(v) for k, v in extra_params.items()})
        sep = "&" if "?" in endpoint else "?"
        return f"{endpoint}{sep}{urlencode(params)}"

    def exchange_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        return self._token_request(
            grant_type="authorization_code",
            payload={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )

    def refresh(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> dict[str, Any]:
        return self._token_request(
            grant_type="refresh_token",
            payload={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )

    def client_credentials(
        self,
        *,
        client_id: str,
        client_secret: str,
        audience: str | None = None,
        scope: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, str] = {
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if audience:
            payload["audience"] = audience
        if scope:
            payload["scope"] = scope
        if extra:
            payload.update(extra)
        return self._token_request(grant_type="client_credentials", payload=payload)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _token_request(self, *, grant_type: str, payload: dict[str, str]) -> dict[str, Any]:
        meta = self.discovery()
        endpoint = str(meta.get("token_endpoint") or "").strip()
        if not endpoint:
            raise OidcClientError("Discovery document has no token_endpoint")
        body = {**payload, "grant_type": grant_type}
        try:
            response = self._client.post(
                endpoint,
                data=body,
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise OidcClientError(f"POST {endpoint} failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text[:500]}

        if response.status_code >= 400:
            error = (
                data.get("error_description")
                or data.get("error")
                or f"HTTP {response.status_code}"
            )
            raise TokenExchangeError(
                f"token endpoint {endpoint} returned {response.status_code}: {error}"
            )
        if not isinstance(data, dict):
            raise OidcClientError(f"token endpoint {endpoint} returned non-dict body")
        return data


__all__ = [
    "DiscoveryUnavailableError",
    "OidcClientError",
    "OidcHttpClient",
    "TokenExchangeError",
    "reset_discovery_cache",
]
