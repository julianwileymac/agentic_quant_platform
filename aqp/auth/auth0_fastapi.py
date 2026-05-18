"""Optional Auth0FastAPI instance for scope-checked dependencies.

Returns a cached ``Auth0FastAPI`` (from ``auth0-fastapi-api``) when
``settings.auth_provider == "auth0"`` and the SDK is importable. When the
provider is anything else (msal_entra, oidc, mock, local), or the SDK is not
installed, returns ``None``.
"""
from __future__ import annotations

import logging
import threading

from aqp.config import settings

logger = logging.getLogger(__name__)

_AUTH0: object | None = None
_AUTH0_LOCK = threading.RLock()
_AUTH0_TRIED = False


def get_auth0_fastapi() -> object | None:
    """Return the cached :class:`Auth0FastAPI` instance, or ``None``."""
    global _AUTH0
    global _AUTH0_TRIED
    if _AUTH0 is not None:
        return _AUTH0
    with _AUTH0_LOCK:
        if _AUTH0 is not None:
            return _AUTH0
        provider = str(settings.auth_provider or "").lower()
        if provider != "auth0":
            return None
        issuer = str(settings.auth_oidc_issuer or "").strip()
        audience = str(settings.auth_oidc_audience or "").strip()
        domain = _issuer_to_domain(issuer)
        if not domain or not audience:
            logger.warning("Auth0FastAPI disabled: auth_oidc_issuer/auth_oidc_audience missing")
            return None
        if _AUTH0_TRIED:
            return None
        try:
            from fastapi_plugin.fast_api_client import Auth0FastAPI
        except Exception:  # noqa: BLE001 - optional dependency
            _AUTH0_TRIED = True
            logger.warning("auth0-fastapi-api SDK unavailable; falling back to multi-provider deps")
            return None
        _AUTH0_TRIED = True
        _AUTH0 = Auth0FastAPI(domain=domain, audience=audience)
        return _AUTH0


def reset_auth0_fastapi() -> None:
    """Drop the cached instance. Tests use this when flipping settings."""
    global _AUTH0
    global _AUTH0_TRIED
    with _AUTH0_LOCK:
        _AUTH0 = None
        _AUTH0_TRIED = False


def _issuer_to_domain(issuer: str) -> str:
    normalized = issuer.strip()
    if normalized.startswith("https://"):
        normalized = normalized[len("https://") :]
    elif normalized.startswith("http://"):
        normalized = normalized[len("http://") :]
    return normalized.strip().strip("/")


__all__ = ["get_auth0_fastapi", "reset_auth0_fastapi"]
