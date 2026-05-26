"""PomeriumAccessProvider — validates ``X-Pomerium-Jwt-Assertion`` tokens.

Phase 4 §7.5 (RESTRUCTURING_PLAN.md). Pomerium is an identity-aware
proxy that sits in front of ``/manage/*`` and ``aqp_admin/``. It:

1. Validates the user's primary IdP token (Auth0 / Entra) at the edge.
2. Performs the step-up MFA prompt (Rule 52) before forwarding.
3. Adds an ``X-Pomerium-Jwt-Assertion`` header signed by Pomerium so
   backend services can verify the proxy decision audit-trail.

The provider mirrors :class:`aqp.auth.providers.cloudflare_access.CloudflareAccessProvider`
because the architectures are isomorphic — both are edge IAPs that
inject signed headers and don't expose OIDC user flows themselves.

The provider does NOT implement :meth:`login_url` /
:meth:`exchange_code` / :meth:`m2m_token` — those happen inside
Pomerium, not in AQP. Calling them raises
:class:`IdentityProviderError`.

Wire-up:

- Run with the upstream Auth0 / Entra provider active for ``/auth/*``
  flows, and chain Pomerium for the ``/manage/*`` enforcement path.
- Operator sets ``AQP_POMERIUM_AUTHENTICATE_URL`` (the Pomerium
  authenticate service URL) + ``AQP_POMERIUM_JWT_AUDIENCE`` (the
  audience claim Pomerium signs into the assertion). Pomerium's
  JWKS lives at ``https://<authenticate-url>/.well-known/pomerium/jwks.json``.
- :func:`extract_pomerium_claims` is called from
  :mod:`aqp.api.security` to enrich the
  :class:`aqp.auth.context.RequestContext` with Pomerium claims when
  the route is fronted by Pomerium.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from aqp.auth.providers.protocol import (
    IdentityProvider,
    IdentityProviderConfig,
    IdentityProviderError,
    M2MTokenResult,
    TokenResponse,
)

logger = logging.getLogger(__name__)


# JWKS cache (Pomerium rotates keys daily by default).
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_LOCK = threading.RLock()
_JWKS_TTL_SECONDS = 3600  # 1h cache


_DEFAULT_HEADER_NAME = "x-pomerium-jwt-assertion"


def _authenticate_url(config: IdentityProviderConfig | None = None) -> str:
    if config is not None and config.issuer:
        return str(config.issuer).strip().rstrip("/")
    return os.environ.get("AQP_POMERIUM_AUTHENTICATE_URL", "").strip().rstrip("/")


def _audience(config: IdentityProviderConfig | None = None) -> str:
    if config is not None and config.audience:
        return str(config.audience).strip()
    return os.environ.get("AQP_POMERIUM_JWT_AUDIENCE", "").strip()


def _jwks_url(authenticate_url: str) -> str:
    base = authenticate_url
    if not base.startswith("http"):
        base = f"https://{base}"
    return f"{base}/.well-known/pomerium/jwks.json"


def _fetch_jwks(authenticate_url: str) -> dict[str, Any]:
    """Pull Pomerium's JWKS from the authenticate service (cached)."""
    cache_key = authenticate_url
    with _JWKS_LOCK:
        cached = _JWKS_CACHE.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < _JWKS_TTL_SECONDS:
            return cached[1]
    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise IdentityProviderError(
            "httpx not available for Pomerium JWKS fetch"
        ) from exc
    url = _jwks_url(authenticate_url)
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise IdentityProviderError(
            f"Pomerium JWKS fetch failed ({url}): {exc}"
        ) from exc
    with _JWKS_LOCK:
        _JWKS_CACHE[cache_key] = (time.monotonic(), body)
    return body


def _decode_jwt(
    token: str,
    *,
    jwks: dict[str, Any],
    audience: str,
    issuer: str,
) -> dict[str, Any]:
    """Decode + validate the Pomerium assertion JWT."""
    try:
        import jwt  # type: ignore[import-not-found]
        from jwt import PyJWKSet  # type: ignore[import-not-found]
        from jwt.exceptions import InvalidTokenError  # type: ignore[import-not-found]
    except ImportError as exc:
        raise IdentityProviderError(
            "PyJWT not installed (pip install 'pyjwt[crypto]')"
        ) from exc

    try:
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
    except Exception as exc:  # noqa: BLE001
        raise IdentityProviderError(f"Pomerium JWT header invalid: {exc}") from exc

    key = None
    try:
        jwkset = PyJWKSet.from_dict(jwks)
        if kid:
            for k in jwkset.keys:
                if k.key_id == kid:
                    key = k.key
                    break
        if key is None and jwkset.keys:
            key = jwkset.keys[0].key
    except Exception as exc:  # noqa: BLE001
        raise IdentityProviderError(f"Pomerium JWKS parse failed: {exc}") from exc

    if key is None:
        raise IdentityProviderError(
            f"Pomerium JWT kid={kid!r} not in JWKS"
        )

    try:
        payload = jwt.decode(
            token,
            key=key,
            algorithms=["ES256", "RS256"],
            audience=audience,
            issuer=issuer,
            options={
                "require": ["exp", "iat", "aud", "iss"],
                "verify_aud": True,
                "verify_iss": True,
                "verify_signature": True,
                "verify_exp": True,
            },
        )
    except InvalidTokenError as exc:
        raise IdentityProviderError(f"Pomerium JWT invalid: {exc}") from exc
    return payload


def extract_pomerium_claims(
    request: Any,
    *,
    authenticate_url: str | None = None,
    audience: str | None = None,
    header_name: str | None = None,
) -> dict[str, Any] | None:
    """Validate the ``X-Pomerium-Jwt-Assertion`` header on ``request``.

    Returns the decoded claims dict, or ``None`` when:

    - the header is missing (request did not come through Pomerium), or
    - the provider is not configured (``AQP_POMERIUM_*`` env vars empty), or
    - the JWT fails signature / audience / issuer validation (logged).

    Mirrors :func:`extract_cloudflare_access_claims` so the existing
    auth chain in :mod:`aqp.api.security` can layer Pomerium on top of
    its current provider without changing the user-flow code paths.
    """
    headers = getattr(request, "headers", {}) or {}
    hdr_name = (header_name or _DEFAULT_HEADER_NAME).lower()
    token = headers.get(hdr_name)
    if not token and hasattr(headers, "items"):
        # Some frameworks return header dicts that aren't case-insensitive.
        for k, v in headers.items():
            if k.lower() == hdr_name:
                token = v
                break
    if not token:
        return None
    auth_url = (authenticate_url or _authenticate_url() or "").strip()
    aud = (audience or _audience() or "").strip()
    if not auth_url or not aud:
        return None
    try:
        jwks = _fetch_jwks(auth_url)
        issuer = auth_url if auth_url.startswith("http") else f"https://{auth_url}"
        return _decode_jwt(token, jwks=jwks, audience=aud, issuer=issuer)
    except IdentityProviderError as exc:
        logger.warning("Pomerium JWT rejected: %s", exc)
        return None


class PomeriumAccessProvider(IdentityProvider):
    """Resource-server-only :class:`IdentityProvider` for Pomerium.

    Validates the ``X-Pomerium-Jwt-Assertion`` header but does NOT
    implement the user-facing OIDC flows. ``login_url`` /
    ``exchange_code`` / ``refresh`` / ``m2m_token`` raise
    :class:`IdentityProviderError` — those flows happen inside the
    Pomerium authenticate service, not inside AQP.
    """

    provider_kind = "pomerium"
    provider_alias = "PomeriumAccessProvider"

    def __init__(self, config: IdentityProviderConfig | None = None) -> None:
        cfg = config or IdentityProviderConfig(
            issuer=os.environ.get("AQP_POMERIUM_AUTHENTICATE_URL", "").strip(),
            audience=os.environ.get("AQP_POMERIUM_JWT_AUDIENCE", "").strip(),
        )
        super().__init__(cfg)

    # ------------------------------------------------------------------
    # IdentityProvider
    # ------------------------------------------------------------------

    def discovery(self) -> dict[str, Any]:
        auth_url = _authenticate_url(self.config)
        return {
            "issuer": auth_url,
            "jwks_uri": _jwks_url(auth_url),
            "audience": _audience(self.config),
        }

    def jwks(self) -> dict[str, Any]:
        auth_url = _authenticate_url(self.config)
        return _fetch_jwks(auth_url)

    def login_url(self, **_kwargs: Any) -> str:  # type: ignore[override]
        raise IdentityProviderError(
            "PomeriumAccessProvider is edge-only; configure Auth0 / Entra "
            "for user-facing OIDC and chain Pomerium for /manage/* gate."
        )

    def exchange_code(self, **_kwargs: Any) -> TokenResponse:  # type: ignore[override]
        raise IdentityProviderError("PomeriumAccessProvider is edge-only")

    def refresh(self, refresh_token: str) -> TokenResponse:  # noqa: ARG002
        raise IdentityProviderError("PomeriumAccessProvider is edge-only")

    def logout_url(self, **_kwargs: Any) -> str:  # type: ignore[override]
        raise IdentityProviderError("PomeriumAccessProvider is edge-only")

    def m2m_token(
        self,
        *,
        audience: str | None = None,  # noqa: ARG002
        scope: str | None = None,  # noqa: ARG002
    ) -> M2MTokenResult:
        raise IdentityProviderError(
            "PomeriumAccessProvider does not mint M2M tokens"
        )

    def describe(self) -> dict[str, Any]:
        out = super().describe()
        out.update(
            {
                "authenticate_url": _authenticate_url(self.config),
                "audience": _audience(self.config),
                "jwks_url": _jwks_url(_authenticate_url(self.config))
                if _authenticate_url(self.config)
                else "",
            }
        )
        return out


__all__ = ["PomeriumAccessProvider", "extract_pomerium_claims"]
