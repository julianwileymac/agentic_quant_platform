"""Validator singleton for the control plane.

Wraps :class:`aqp_platform_core.auth.JwtValidator` so the FastAPI
process gets one shared JWKS cache across all requests.
"""
from __future__ import annotations

import asyncio
from typing import Any

from aqp_platform_core.auth import (
    JwtValidationError,
    JwtValidator,
    JwtValidatorConfig,
)

from aqp_cp.settings import get_settings

_VALIDATOR: JwtValidator | None = None
_LOCK = asyncio.Lock()


async def get_validator() -> JwtValidator | None:
    """Return the active validator, or ``None`` when auth is disabled."""
    global _VALIDATOR
    settings = get_settings()
    if not settings.auth_enabled:
        return None
    if _VALIDATOR is not None:
        return _VALIDATOR
    async with _LOCK:
        if _VALIDATOR is None:
            _VALIDATOR = JwtValidator(
                JwtValidatorConfig(
                    issuer=settings.auth_oidc_issuer,
                    audience=settings.auth_oidc_audience,
                    leeway_seconds=settings.auth_leeway_seconds,
                    jwks_ttl_seconds=settings.auth_jwks_ttl_seconds,
                )
            )
    return _VALIDATOR


async def reset_validator() -> None:
    """Drop the validator singleton (test helper + shutdown hook)."""
    global _VALIDATOR
    async with _LOCK:
        if _VALIDATOR is not None:
            await _VALIDATOR.close()
            _VALIDATOR = None


async def validate_bearer_token(token: str) -> dict[str, Any]:
    """Convenience helper — validate a bearer token end-to-end."""
    validator = await get_validator()
    if validator is None:
        raise JwtValidationError(
            "auth disabled on this control plane instance",
            code="auth_disabled",
        )
    return await validator.validate(token)


__all__ = ["get_validator", "reset_validator", "validate_bearer_token"]
