"""CloudflareAccessProvider — validates ``Cf-Access-Jwt-Assertion`` tokens.

Cloudflare Access sits at the edge: every request that reaches AQP
already came through a Cloudflare Tunnel + an Access app, and the edge
adds a ``Cf-Access-Jwt-Assertion`` header signed by Cloudflare. This
provider validates that header against the team's JWKS so AQP can
accept either an Auth0 access token OR a Cloudflare-Access JWT (or
both) depending on the configured edge.

Public key endpoint::

    https://<team>.cloudflareaccess.com/cdn-cgi/access/certs

Keys rotate every 6 weeks; previous keys stay valid for 7 days. We
cache the JWKS in-process and refresh on signature mismatch.

The provider does NOT support :meth:`login_url` / :meth:`exchange_code`
/ :meth:`m2m_token` — those flows happen at the Cloudflare edge, not
inside AQP. Calling them raises :class:`IdentityProviderError`.

Wire-up:

- Set ``AQP_AUTH_PROVIDER=cloudflare_access`` to make this the active
  provider (resource-server only mode).
- Set ``AQP_CF_ACCESS_TEAM_DOMAIN`` (the Cloudflare team domain
  without ``.cloudflareaccess.com``) + ``AQP_CF_ACCESS_AUD`` (the
  Application Audience tag).
- Or run in chained mode: keep the Auth0 / MSAL provider active for
  ``/auth/*`` flows and let
  :func:`extract_cloudflare_access_claims` (called from
  :mod:`aqp.api.security`) honour the header on every request.
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


_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_LOCK = threading.RLock()
_JWKS_TTL_SECONDS = 6 * 3600  # 6h cache — keys rotate every ~6 weeks.


def cf_team_domain(config: IdentityProviderConfig | None = None) -> str:
    """Return the Cloudflare team domain (without ``.cloudflareaccess.com``)."""
    if config is not None and config.issuer:
        issuer = str(config.issuer).strip().rstrip("/")
        # Issuer might be the full ``https://<team>.cloudflareaccess.com``.
        if "cloudflareaccess.com" in issuer:
            host = issuer.split("//", 1)[-1].split("/", 1)[0]
            return host.split(".cloudflareaccess.com", 1)[0]
        return issuer
    return os.environ.get("AQP_CF_ACCESS_TEAM_DOMAIN", "").strip()


def cf_audience(config: IdentityProviderConfig | None = None) -> str:
    if config is not None and config.audience:
        return str(config.audience).strip()
    return os.environ.get("AQP_CF_ACCESS_AUD", "").strip()


def _certs_url(team_domain: str) -> str:
    if team_domain.startswith("http"):
        base = team_domain.rstrip("/")
    else:
        base = f"https://{team_domain}.cloudflareaccess.com"
    return f"{base}/cdn-cgi/access/certs"


def _fetch_jwks(team_domain: str) -> dict[str, Any]:
    """Pull the JWKS from the Cloudflare certs endpoint (cached)."""
    cache_key = team_domain
    with _JWKS_LOCK:
        cached = _JWKS_CACHE.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < _JWKS_TTL_SECONDS:
            return cached[1]
    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - httpx is a hard AQP dep
        raise IdentityProviderError(
            "httpx not available for Cloudflare Access JWKS fetch"
        ) from exc
    url = _certs_url(team_domain)
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise IdentityProviderError(
            f"Cloudflare Access JWKS fetch failed ({url}): {exc}"
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
    """Decode and validate a Cloudflare Access JWT."""
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
        raise IdentityProviderError(f"Cf-Access JWT header invalid: {exc}") from exc

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
        raise IdentityProviderError(f"Cf-Access JWKS parse failed: {exc}") from exc

    if key is None:
        raise IdentityProviderError(
            f"Cf-Access JWT kid={kid!r} not in JWKS"
        )

    try:
        payload = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
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
        raise IdentityProviderError(f"Cf-Access JWT invalid: {exc}") from exc
    return payload


def extract_cloudflare_access_claims(
    request: Any,
    *,
    team_domain: str | None = None,
    audience: str | None = None,
) -> dict[str, Any] | None:
    """Validate the ``Cf-Access-Jwt-Assertion`` header on ``request``.

    Returns the decoded claims dict, or ``None`` when:

    - the header is missing (request did not come through Cloudflare Access), or
    - the provider is not configured (``AQP_CF_ACCESS_*`` env vars empty), or
    - the JWT fails signature / audience / issuer validation (logged).

    Used by :mod:`aqp.api.security` to enrich the active
    :class:`aqp.auth.context.RequestContext` with Cloudflare Access
    claims when the AQP edge is fronted by Cloudflare.
    """
    headers = getattr(request, "headers", {}) or {}
    token = headers.get("cf-access-jwt-assertion") or headers.get(
        "Cf-Access-Jwt-Assertion"
    )
    if not token:
        return None
    team = (team_domain or cf_team_domain() or "").strip()
    aud = (audience or cf_audience() or "").strip()
    if not team or not aud:
        return None
    try:
        jwks = _fetch_jwks(team)
        issuer = (
            team if team.startswith("http") else f"https://{team}.cloudflareaccess.com"
        )
        return _decode_jwt(
            token, jwks=jwks, audience=aud, issuer=issuer
        )
    except IdentityProviderError as exc:
        logger.warning("Cf-Access JWT rejected: %s", exc)
        return None


class CloudflareAccessProvider(IdentityProvider):
    """Resource-server-only :class:`IdentityProvider` for Cloudflare Access.

    Validates the ``Cf-Access-Jwt-Assertion`` header but does NOT
    implement the user-facing OIDC flows. ``login_url`` /
    ``exchange_code`` / ``refresh`` / ``m2m_token`` raise
    :class:`IdentityProviderError` — those flows happen at the
    Cloudflare edge, not inside AQP.
    """

    provider_kind = "cloudflare_access"
    provider_alias = "CloudflareAccessProvider"

    def __init__(self, config: IdentityProviderConfig | None = None) -> None:
        cfg = config or IdentityProviderConfig(
            issuer=os.environ.get("AQP_CF_ACCESS_TEAM_DOMAIN", "").strip(),
            audience=os.environ.get("AQP_CF_ACCESS_AUD", "").strip(),
        )
        super().__init__(cfg)

    def discovery(self) -> dict[str, Any]:
        team = cf_team_domain(self.config)
        base = (
            team
            if team.startswith("http")
            else f"https://{team}.cloudflareaccess.com"
        )
        return {
            "issuer": base,
            "jwks_uri": _certs_url(team),
            "id_token_signing_alg_values_supported": ["RS256"],
            "response_types_supported": [],
            "grant_types_supported": [],
        }

    def jwks(self) -> dict[str, Any]:
        team = cf_team_domain(self.config)
        if not team:
            return {"keys": []}
        try:
            return _fetch_jwks(team)
        except IdentityProviderError as exc:
            logger.warning("Cf-Access jwks() failed: %s", exc)
            return {"keys": []}

    def login_url(self, **_kwargs: Any) -> str:
        raise IdentityProviderError(
            "CloudflareAccessProvider does not implement login_url; the "
            "user-facing flow lives at the Cloudflare edge."
        )

    def exchange_code(self, **_kwargs: Any) -> TokenResponse:
        raise IdentityProviderError(
            "CloudflareAccessProvider does not implement exchange_code; "
            "Cloudflare Access mints the JWT itself."
        )

    def refresh(self, refresh_token: str) -> TokenResponse:
        raise IdentityProviderError(
            "CloudflareAccessProvider does not implement refresh; "
            "Cloudflare Access rotates the JWT via the edge cookie."
        )

    def logout_url(self, **_kwargs: Any) -> str:
        team = cf_team_domain(self.config)
        base = (
            team
            if team.startswith("http")
            else f"https://{team}.cloudflareaccess.com"
        )
        return f"{base}/cdn-cgi/access/logout"

    def m2m_token(self, **_kwargs: Any) -> M2MTokenResult:
        raise IdentityProviderError(
            "CloudflareAccessProvider does not mint M2M tokens; use "
            "Cloudflare service tokens (Client-Id + Client-Secret headers)."
        )

    def validate_request(self, request: Any) -> dict[str, Any] | None:
        """Validate ``Cf-Access-Jwt-Assertion`` on ``request`` and return claims."""
        return extract_cloudflare_access_claims(
            request,
            team_domain=cf_team_domain(self.config),
            audience=cf_audience(self.config),
        )


__all__ = [
    "CloudflareAccessProvider",
    "extract_cloudflare_access_claims",
]
