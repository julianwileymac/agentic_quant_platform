"""Auth0 JWT validation for the rpi_kubernetes management API.

This is intentionally tiny — a single ``validate_jwt`` helper +
``require_authenticated`` FastAPI dep, gated behind ``APP_AUTH_PROVIDER``.
The implementation mirrors :mod:`aqp.auth.oidc` (same wire protocol,
same JWKS caching pattern) so an Auth0 tenant can serve both AQP and
the management plane from one Application + API audience pair.

Three modes via ``APP_AUTH_PROVIDER``:

- ``none`` (default) — every request passes, matches the legacy
  ``cors_origins=["*"]`` posture so local dev keeps working.
- ``auth0`` — strict JWT validation against the configured tenant.
- ``cloudflare_access`` — trust the ``Cf-Access-Authenticated-User-Email``
  header injected by Cloudflare Access. Useful when the management
  plane lives behind an Access policy and the user has no AQP JWT.

Both ``auth0`` and ``cloudflare_access`` raise 401 on missing /
invalid identity. The default ``none`` mode is the existing behaviour
so the rollout is opt-in.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Module-level JWKS cache keyed by JWKS URL — identical contract to
# aqp.auth.oidc._JWKS_CACHE so a future shared library can replace
# both with a single implementation.
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_LOCK = threading.Lock()


@dataclass(frozen=True)
class MgmtOidcConfig:
    issuer: str
    audience: str
    jwks_ttl_seconds: int = 3600
    leeway_seconds: int = 60

    @property
    def jwks_uri(self) -> str:
        base = self.issuer.rstrip("/")
        if base.endswith("/.well-known/jwks.json"):
            return base
        return f"{base}/.well-known/jwks.json"


def _env(key: str, default: str = "") -> str:
    return str(os.environ.get(key, default) or default).strip()


def _build_config() -> MgmtOidcConfig | None:
    """Read ``APP_AUTH_*`` env vars into a frozen config snapshot."""
    issuer = _env("APP_AUTH_OIDC_ISSUER")
    audience = _env("APP_AUTH_OIDC_AUDIENCE")
    if not issuer or not audience:
        return None
    return MgmtOidcConfig(
        issuer=issuer,
        audience=audience,
        jwks_ttl_seconds=int(_env("APP_AUTH_OIDC_JWKS_TTL_SECONDS", "3600") or 3600),
        leeway_seconds=int(_env("APP_AUTH_OIDC_LEEWAY_SECONDS", "60") or 60),
    )


def _fetch_jwks(config: MgmtOidcConfig) -> dict[str, Any]:
    now = time.time()
    cached = _JWKS_CACHE.get(config.jwks_uri)
    if cached is not None and now < cached[0]:
        return cached[1]
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(config.jwks_uri)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        if cached is not None:
            logger.warning("JWKS fetch failed (%s); serving stale", exc)
            return cached[1]
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"JWKS unreachable: {exc}",
        ) from exc
    if not isinstance(payload, dict) or "keys" not in payload:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invalid JWKS document",
        )
    with _JWKS_LOCK:
        _JWKS_CACHE[config.jwks_uri] = (
            now + max(60, config.jwks_ttl_seconds),
            payload,
        )
    return payload


def _select_signing_key(jwks: dict[str, Any], kid: str | None) -> dict[str, Any]:
    keys = jwks.get("keys") or []
    if not keys:
        raise HTTPException(status_code=401, detail="JWKS has no signing keys")
    if kid:
        for key in keys:
            if key.get("kid") == kid:
                return key
        raise HTTPException(status_code=401, detail=f"JWT kid {kid!r} not found")
    if len(keys) == 1:
        return keys[0]
    raise HTTPException(
        status_code=401, detail="JWT has no kid header but JWKS contains multiple keys"
    )


def validate_jwt(token: str, config: MgmtOidcConfig | None = None) -> dict[str, Any]:
    """Verify *token* and return its claims dict.

    Mirrors :func:`aqp.auth.oidc.validate_jwt` but locally re-implemented
    so the management plane has no AQP runtime dependency.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Empty token")
    cfg = config or _build_config()
    if cfg is None:
        raise HTTPException(
            status_code=503,
            detail="Auth0 not configured — set APP_AUTH_OIDC_ISSUER + APP_AUTH_OIDC_AUDIENCE",
        )
    try:
        from jose import jwt as jose_jwt
        from jose.exceptions import JWTError
    except ImportError as exc:  # pragma: no cover - dep guard
        raise HTTPException(
            status_code=500,
            detail="python-jose is required for Auth0 mode",
        ) from exc

    header = jose_jwt.get_unverified_header(token)
    jwks = _fetch_jwks(cfg)
    signing_key = _select_signing_key(jwks, header.get("kid"))
    issuer_variants = {cfg.issuer.rstrip("/"), cfg.issuer.rstrip("/") + "/"}

    try:
        claims = jose_jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=cfg.audience,
            options={"verify_at_hash": False, "leeway": int(cfg.leeway_seconds)},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"JWT verification failed: {exc}",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from exc

    iss = str(claims.get("iss") or "")
    if iss not in issuer_variants and iss.rstrip("/") not in {
        v.rstrip("/") for v in issuer_variants
    }:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"JWT issuer {iss!r} does not match {cfg.issuer!r}",
        )
    return claims


# ---------------------------------------------------------------------------
# FastAPI dep — single point of enforcement
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


def require_authenticated_mgmt(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    cf_access_email: str | None = Header(
        default=None, alias="Cf-Access-Authenticated-User-Email"
    ),
) -> dict[str, Any]:
    """Reject unauthenticated requests when ``APP_AUTH_PROVIDER`` is enabled.

    Returns the verified principal dict (claims, or
    ``{"email": cf_access_email}`` for Cloudflare Access).
    """
    provider = _env("APP_AUTH_PROVIDER", "none").lower()
    if provider == "none":
        return {"provider": "none"}

    if provider == "cloudflare_access":
        if not cf_access_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cloudflare Access header missing",
            )
        return {"provider": "cloudflare_access", "email": cf_access_email}

    if provider == "auth0":
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        claims = validate_jwt(credentials.credentials)
        # Stash on request state so downstream handlers can read
        # additional claims without re-verifying.
        request.state.oidc_claims = claims
        return {"provider": "auth0", **claims}

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Unknown APP_AUTH_PROVIDER={provider!r}",
    )


__all__ = [
    "MgmtOidcConfig",
    "require_authenticated_mgmt",
    "validate_jwt",
]
