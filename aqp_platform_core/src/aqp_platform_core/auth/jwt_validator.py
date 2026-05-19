"""JWKS-backed RS256 JWT validator (Auth0-compatible).

Mirrors the validator semantics inside ``aqp/auth/providers/auth0.py``
+ ``aqp/api/security.py`` so the same logic runs unchanged inside
``aqp_control_plane`` without importing from ``aqp.*``.

Usage:

    config = JwtValidatorConfig(
        issuer="https://my-tenant.us.auth0.com/",
        audience="https://api.aqp.internal/manage",
    )
    validator = JwtValidator(config)
    payload = await validator.validate(bearer_token)

The validator caches the JWKS in-memory (no Redis, no SQLite); the
short TTL + lazy refresh on signature mismatch covers Auth0's signing
key rotation.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from jose import jwt
from jose.exceptions import JWTError
from jose.utils import base64url_decode

logger = logging.getLogger(__name__)


class JwtValidationError(Exception):
    """Raised when a token fails validation (invalid signature, expired, wrong aud, etc.)."""

    def __init__(self, message: str, *, code: str = "invalid_token") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class JwtValidatorConfig:
    """Configuration for :class:`JwtValidator`.

    ``issuer`` is the Auth0 tenant URL (with trailing slash —
    ``https://my-tenant.us.auth0.com/``). ``audience`` is the API
    resource identifier configured in Auth0
    (``https://api.aqp.internal/manage``). The JWKS endpoint is
    derived as ``{issuer}.well-known/jwks.json``.

    ``leeway_seconds`` allows for small clock skew between the
    issuing tenant and the validating service. ``jwks_ttl_seconds``
    bounds how long the JWKS is cached before a forced refresh.
    """

    issuer: str
    audience: str
    algorithms: tuple[str, ...] = ("RS256",)
    leeway_seconds: int = 60
    jwks_ttl_seconds: int = 600
    http_timeout_seconds: float = 10.0
    # Optional explicit JWKS URL — overrides the issuer-derived default.
    jwks_url_override: str = ""
    # Additional claim namespaces to surface unchanged in the payload.
    expected_claim_namespaces: tuple[str, ...] = field(default_factory=tuple)


class JwtValidator:
    """Validate Auth0-issued JWTs against a cached JWKS.

    Thread-safe via a single :class:`asyncio.Lock` around the JWKS
    refresh; per-request validation is lock-free. Suitable for use
    behind FastAPI's request-concurrency model.
    """

    def __init__(self, config: JwtValidatorConfig) -> None:
        self.config = config
        self._jwks: dict[str, Any] | None = None
        self._jwks_loaded_at: float = 0.0
        self._lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    # --- public API ----------------------------------------------------

    @property
    def jwks_url(self) -> str:
        if self.config.jwks_url_override:
            return self.config.jwks_url_override
        issuer = self.config.issuer.rstrip("/")
        return f"{issuer}/.well-known/jwks.json"

    async def validate(self, token: str) -> dict[str, Any]:
        """Validate ``token`` and return its decoded payload.

        Raises :class:`JwtValidationError` on any failure with a
        machine-readable ``code`` ("invalid_token", "expired_token",
        "wrong_issuer", "wrong_audience", "no_matching_key").
        """
        if not token:
            raise JwtValidationError("missing bearer token", code="invalid_request")

        try:
            unverified_header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise JwtValidationError(f"malformed token: {exc}") from exc

        kid = unverified_header.get("kid")
        if not kid:
            raise JwtValidationError("token header missing 'kid'", code="invalid_token")

        key = await self._lookup_key(kid)
        if key is None:
            # Force a refresh once in case Auth0 rotated keys.
            await self._refresh_jwks(force=True)
            key = await self._lookup_key(kid)
            if key is None:
                raise JwtValidationError(
                    f"no JWKS entry for kid={kid!r}", code="no_matching_key"
                )

        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=list(self.config.algorithms),
                audience=self.config.audience,
                issuer=self.config.issuer,
                options={
                    "verify_signature": True,
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                    "leeway": self.config.leeway_seconds,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise JwtValidationError("token expired", code="expired_token") from exc
        except jwt.JWTClaimsError as exc:
            # python-jose lumps wrong-iss/wrong-aud here. Best-effort
            # disambiguation by string match for monitoring.
            text = str(exc).lower()
            code = (
                "wrong_audience"
                if "aud" in text
                else "wrong_issuer"
                if "iss" in text
                else "invalid_claims"
            )
            raise JwtValidationError(str(exc), code=code) from exc
        except JWTError as exc:
            raise JwtValidationError(str(exc)) from exc

        return payload

    async def close(self) -> None:
        """Release the underlying httpx client. Idempotent."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # --- JWKS cache ----------------------------------------------------

    async def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=self.config.http_timeout_seconds,
                headers={"Accept": "application/json"},
            )
        return self._http

    async def _lookup_key(self, kid: str) -> dict[str, Any] | None:
        await self._maybe_refresh_jwks()
        if not self._jwks:
            return None
        for entry in self._jwks.get("keys", []):
            if entry.get("kid") == kid:
                return entry
        return None

    async def _maybe_refresh_jwks(self) -> None:
        if self._jwks is None:
            await self._refresh_jwks(force=False)
            return
        age = time.monotonic() - self._jwks_loaded_at
        if age >= self.config.jwks_ttl_seconds:
            await self._refresh_jwks(force=False)

    async def _refresh_jwks(self, *, force: bool) -> None:
        async with self._lock:
            if self._jwks is not None and not force:
                age = time.monotonic() - self._jwks_loaded_at
                if age < self.config.jwks_ttl_seconds:
                    return
            client = await self._http_client()
            try:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                self._jwks = response.json()
                self._jwks_loaded_at = time.monotonic()
            except httpx.HTTPError as exc:
                logger.warning("JWKS refresh failed: %s", exc)
                if self._jwks is None:
                    raise JwtValidationError(
                        f"failed to fetch JWKS from {self.jwks_url}: {exc}",
                        code="jwks_unreachable",
                    ) from exc

    # --- token introspection helper (no validation) -------------------

    @staticmethod
    def decode_unverified(token: str) -> dict[str, Any]:
        """Decode the payload WITHOUT signature verification.

        Useful for debugging or for non-security-sensitive metadata
        extraction (e.g. logging the sub). NEVER trust the result for
        authz decisions — use :meth:`validate` for those.
        """
        try:
            _, claims_b64, _ = token.split(".")
        except ValueError as exc:
            raise JwtValidationError(f"malformed token: {exc}") from exc
        try:
            import json

            decoded = base64url_decode(claims_b64.encode("ascii"))
            return json.loads(decoded.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise JwtValidationError(f"failed to decode payload: {exc}") from exc


__all__ = [
    "JwtValidationError",
    "JwtValidator",
    "JwtValidatorConfig",
]
