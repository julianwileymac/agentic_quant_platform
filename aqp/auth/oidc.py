"""OIDC / OAuth2 JWT validation seam for AQP.

This module is the swap point referenced by
:mod:`aqp.auth.deps` and :mod:`aqp.auth.user`: when
``settings.auth_provider != "local"`` the FastAPI dep pipeline calls
:func:`validate_jwt` to turn a ``Authorization: Bearer <token>`` header
into a verified claims dict, which :func:`aqp.auth.user.resolve_user`
then maps onto a :class:`aqp.persistence.models_tenancy.User` row
(provisioning a new one if the ``sub`` claim is unknown).

The implementation favors stdlib + ``httpx`` + ``python-jose`` over
heavier all-in-one Auth0 SDKs because:

- The platform only needs **token verification**, not full OIDC
  authorization-code orchestration. The frontend handles the
  authorization-code-with-PKCE flow via the official ``@auth0/auth0-react``
  SDK; the backend only sees the resulting ``Authorization: Bearer``
  header.
- ``python-jose[cryptography]`` is a tiny pure-Python dep with no
  vendor lock-in, so the same code path validates Auth0, Keycloak,
  Authentik, Google directly, or any standard OIDC IdP.
- JWKS caching uses a local TTL so a transient JWKS endpoint outage
  doesn't cascade into a 5xx storm on every request.

Public surface:

- :class:`OIDCConfig` — frozen view of ``settings.auth_oidc_*``.
- :class:`OIDCError` / :class:`InvalidTokenError` /
  :class:`JWKSUnavailableError` — typed failure modes, mapped to HTTP
  401/503 by the FastAPI dep layer.
- :func:`get_oidc_config` — lazy ``Settings`` snapshot; returns ``None``
  if OIDC is not configured.
- :func:`validate_jwt(token)` — verify + decode an access token,
  returning the claims dict on success.
- :func:`reset_jwks_cache` — used by tests / dev rotation.

The module deliberately does **not** hit the database. Provisioning
lives in :mod:`aqp.auth.user`.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OIDCError(Exception):
    """Base class for OIDC verification failures."""


class InvalidTokenError(OIDCError):
    """Token is malformed, expired, or fails signature/audience checks."""


class JWKSUnavailableError(OIDCError):
    """Could not fetch the JWKS document from the issuer."""


# ---------------------------------------------------------------------------
# Config snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OIDCConfig:
    """Lazy snapshot of the ``settings.auth_oidc_*`` knobs.

    Constructed via :func:`get_oidc_config`. Frozen so the JWKS cache
    keys remain stable across resolves.
    """

    issuer: str
    audience: str
    client_id: str
    algorithms: tuple[str, ...] = ("RS256",)
    leeway_seconds: int = 60
    jwks_ttl_seconds: int = 3600

    @property
    def jwks_uri(self) -> str:
        """Standard OIDC JWKS endpoint at ``<issuer>/.well-known/jwks.json``."""
        base = self.issuer.rstrip("/")
        if base.endswith("/.well-known/jwks.json"):
            return base
        return f"{base}/.well-known/jwks.json"


def get_oidc_config() -> OIDCConfig | None:
    """Return the configured :class:`OIDCConfig` or ``None`` if local-only.

    The function is intentionally **not** cached: tests and runtime hot-
    reloaders mutate ``settings`` between assertions and we want each
    call to reflect the current view.
    """
    try:
        from aqp.config import settings
    except Exception:  # pragma: no cover - settings module guaranteed in prod
        return None
    if str(settings.auth_provider).lower() == "local":
        return None
    issuer = (settings.auth_oidc_issuer or "").strip()
    audience = (settings.auth_oidc_audience or "").strip()
    if not issuer or not audience:
        logger.warning(
            "auth_provider=%s but auth_oidc_issuer/auth_oidc_audience are unset; "
            "JWT validation will fail. Set AQP_AUTH_OIDC_ISSUER + AQP_AUTH_OIDC_AUDIENCE.",
            settings.auth_provider,
        )
        return None
    return OIDCConfig(
        issuer=issuer,
        audience=audience,
        client_id=str(settings.auth_oidc_client_id or "").strip(),
    )


# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------


_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_LOCK = Lock()


def reset_jwks_cache() -> None:
    """Drop the JWKS cache (used by tests + the IdP-rotation runbook)."""
    with _JWKS_LOCK:
        _JWKS_CACHE.clear()


def _fetch_jwks(config: OIDCConfig) -> dict[str, Any]:
    """Return the JWKS document, populating + honoring the TTL cache.

    When an :class:`aqp.auth.providers.IdentityProvider` is registered
    we delegate the actual fetch to its :meth:`jwks` method so per-
    provider caching, issuer rules, and telemetry stay uniform. The
    ``OIDCConfig.jwks_uri`` cache below is kept as a thin fallback for
    callers that construct an :class:`OIDCConfig` directly without
    going through the provider layer (e.g. legacy tests).
    """
    now = time.time()
    cached = _JWKS_CACHE.get(config.jwks_uri)
    if cached is not None and now < cached[0]:
        return cached[1]

    try:
        from aqp.auth.providers import get_active_provider

        provider = get_active_provider()
        provider_jwks = provider.jwks()
        if isinstance(provider_jwks, dict) and "keys" in provider_jwks:
            with _JWKS_LOCK:
                _JWKS_CACHE[config.jwks_uri] = (
                    now + max(60, int(config.jwks_ttl_seconds)),
                    provider_jwks,
                )
            return provider_jwks
    except Exception as exc:  # noqa: BLE001
        # The provider layer is best-effort — if it is misconfigured we
        # fall through to the direct fetch below so this layer keeps
        # working in isolation.
        logger.debug("Provider JWKS delegation failed (%s); falling back to direct fetch", exc)

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(config.jwks_uri)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        if cached is not None:
            logger.warning(
                "JWKS fetch failed (%s); serving cached document past TTL", exc
            )
            return cached[1]
        raise JWKSUnavailableError(f"Could not fetch JWKS at {config.jwks_uri}: {exc}") from exc

    if not isinstance(payload, dict) or "keys" not in payload:
        raise JWKSUnavailableError(f"JWKS document at {config.jwks_uri} is not a valid JSON Web Key Set")

    with _JWKS_LOCK:
        _JWKS_CACHE[config.jwks_uri] = (now + max(60, int(config.jwks_ttl_seconds)), payload)
    return payload


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


def _decode_unverified_header(token: str) -> dict[str, Any]:
    """Pull the JWT header without trusting the signature.

    Used to look up the signing key by ``kid`` before verification. The
    body is ignored at this stage.
    """
    try:
        from jose import jwt as jose_jwt
    except ImportError as exc:  # pragma: no cover - dep guard
        raise OIDCError(
            "python-jose is required for OIDC verification; install with "
            "`pip install 'python-jose[cryptography]'` or the [auth] extra"
        ) from exc
    try:
        return jose_jwt.get_unverified_header(token)
    except Exception as exc:  # noqa: BLE001
        raise InvalidTokenError(f"Could not decode JWT header: {exc}") from exc


def _select_signing_key(jwks: dict[str, Any], kid: str | None) -> dict[str, Any]:
    """Return the JWK matching ``kid``; falls back to the only key if there's one."""
    keys = jwks.get("keys") or []
    if not keys:
        raise InvalidTokenError("JWKS has no signing keys")
    if kid:
        for key in keys:
            if key.get("kid") == kid:
                return key
        raise InvalidTokenError(f"JWT kid {kid!r} not found in JWKS")
    if len(keys) == 1:
        return keys[0]
    raise InvalidTokenError("JWT has no kid header but JWKS contains multiple keys")


def validate_jwt(
    token: str,
    config: OIDCConfig | None = None,
) -> dict[str, Any]:
    """Verify *token* and return its claims dict.

    Verification covers (in order): the configured RS256 signature
    against the JWKS, the ``iss`` claim against the configured issuer,
    the ``aud`` claim against the configured API audience, and the
    ``exp`` / ``nbf`` time claims with a small leeway.

    Raises:
        :class:`InvalidTokenError`: token failed signature / claim checks.
        :class:`JWKSUnavailableError`: JWKS endpoint is unreachable and
            no cached document exists.
        :class:`OIDCError`: OIDC is not configured (caller should have
            checked :func:`get_oidc_config` first).
    """
    if not token:
        raise InvalidTokenError("Empty token")

    cfg = config or get_oidc_config()
    if cfg is None:
        raise OIDCError("OIDC is not configured (settings.auth_provider == 'local')")

    try:
        from jose import jwt as jose_jwt
        from jose.exceptions import JWTError
    except ImportError as exc:  # pragma: no cover - dep guard
        raise OIDCError(
            "python-jose is required for OIDC verification; install with "
            "`pip install 'python-jose[cryptography]'` or the [auth] extra"
        ) from exc

    header = _decode_unverified_header(token)
    jwks = _fetch_jwks(cfg)
    signing_key = _select_signing_key(jwks, header.get("kid"))

    issuer_variants = {cfg.issuer.rstrip("/"), cfg.issuer.rstrip("/") + "/"}

    try:
        claims = jose_jwt.decode(
            token,
            signing_key,
            algorithms=list(cfg.algorithms),
            audience=cfg.audience,
            options={"verify_at_hash": False, "leeway": int(cfg.leeway_seconds)},
        )
    except JWTError as exc:
        raise InvalidTokenError(f"JWT verification failed: {exc}") from exc

    iss = str(claims.get("iss") or "")
    if iss not in issuer_variants and iss.rstrip("/") not in {v.rstrip("/") for v in issuer_variants}:
        raise InvalidTokenError(f"JWT issuer {iss!r} does not match {cfg.issuer!r}")

    return claims


# ---------------------------------------------------------------------------
# Userinfo helpers
# ---------------------------------------------------------------------------


def claims_email(claims: dict[str, Any]) -> str | None:
    """Best-effort email pull from a verified claims dict.

    Auth0 / Google put it on ``email``; some IdPs nest it under
    ``https://<namespace>/email`` custom claims. Return the first
    plausible value.
    """
    direct = claims.get("email")
    if isinstance(direct, str) and direct.strip():
        return direct.strip().lower()
    for key, value in claims.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key.endswith("/email") and value.strip():
            return value.strip().lower()
    return None


def claims_display_name(claims: dict[str, Any]) -> str:
    """Best-effort display-name pull (``name`` then ``nickname`` then email)."""
    for key in ("name", "nickname", "preferred_username", "given_name"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    email = claims_email(claims)
    if email:
        return email.split("@", 1)[0]
    sub = str(claims.get("sub") or "")
    return sub.split("|", 1)[-1] if sub else "user"


def claims_picture(claims: dict[str, Any]) -> str | None:
    """Optional avatar URL from the standard ``picture`` claim."""
    value = claims.get("picture")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def claims_subject(claims: dict[str, Any]) -> str:
    """Required: the OIDC ``sub`` claim, the canonical user identifier."""
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise InvalidTokenError("JWT is missing the required 'sub' claim")
    return sub.strip()


def claims_provider(claims: dict[str, Any]) -> str:
    """Synthesise an ``auth_provider`` label from the ``sub`` claim.

    Auth0 prefixes connection providers in the sub: ``google-oauth2|...``,
    ``github|...``, ``auth0|...``. Strip the right-hand identifier and
    return the connection type, falling back to ``oidc`` for IdPs that
    don't follow this convention.
    """
    sub = str(claims.get("sub") or "")
    if "|" in sub:
        prefix = sub.split("|", 1)[0]
        if prefix in {"google-oauth2", "github", "windowslive", "facebook", "twitter"}:
            return f"oauth_{prefix.replace('-oauth2', '')}"
        if prefix == "auth0":
            return "auth0"
        return f"oauth_{prefix}"
    iss = str(claims.get("iss") or "").lower()
    if "google" in iss:
        return "oauth_google"
    if "auth0.com" in iss:
        return "auth0"
    return "oidc"


# Re-export convenient names.
__all__ = [
    "InvalidTokenError",
    "JWKSUnavailableError",
    "OIDCConfig",
    "OIDCError",
    "claims_display_name",
    "claims_email",
    "claims_picture",
    "claims_provider",
    "claims_subject",
    "get_oidc_config",
    "reset_jwks_cache",
    "validate_jwt",
]
