"""Optional Auth0FastAPI instance for scope-checked dependencies.

Returns a cached ``Auth0FastAPI`` (from ``auth0-fastapi-api``) when
``settings.auth_provider == "auth0"`` and the SDK is importable. When the
provider is anything else (msal_entra, oidc, mock, local), or the SDK is not
installed, returns ``None``.

Phase E of the Management Engine flips two SDK knobs:

- ``app.state.trust_proxy = True`` so the SDK trusts ``X-Forwarded-*``
  headers (every AQP deployment is fronted by Cloudflare Tunnel +
  nginx-ingress).
- DPoP enabled in **mixed mode** (accepts both Bearer and DPoP tokens)
  — this lets the SPA + Theia migrate to DPoP without breaking
  existing service-token callers.
"""
from __future__ import annotations

import logging
import os
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
        # Mixed-mode DPoP: accept both Bearer and DPoP tokens by default.
        # Operators can flip ``AQP_AUTH0_DPOP_REQUIRED=true`` to reject
        # Bearer once every client has migrated.
        dpop_required = (
            str(os.environ.get("AQP_AUTH0_DPOP_REQUIRED", "")).lower()
            in ("1", "true", "yes")
        )
        dpop_enabled = (
            str(os.environ.get("AQP_AUTH0_DPOP_ENABLED", "true")).lower()
            in ("1", "true", "yes")
        )
        try:
            _AUTH0 = Auth0FastAPI(
                domain=domain,
                audience=audience,
                dpop_enabled=dpop_enabled,
                dpop_required=dpop_required,
            )
        except TypeError:
            # Older SDK signature without DPoP kwargs.
            _AUTH0 = Auth0FastAPI(domain=domain, audience=audience)
        return _AUTH0


def configure_auth0_fastapi_on_app(app: object) -> None:
    """Mark the FastAPI app so the SDK trusts ``X-Forwarded-*`` headers.

    Every AQP deployment terminates TLS at Cloudflare and re-proxies via
    nginx-ingress / cloudflared. Without this knob the DPoP path
    rejects every request because the URL the SDK reconstructs differs
    from the URL the client signed. Called once from ``aqp.api.main``
    AFTER the FastAPI app object is built.
    """
    try:
        state = getattr(app, "state", None)
        if state is None:
            return
        state.trust_proxy = True
    except Exception:  # noqa: BLE001 - never fail boot on this
        logger.debug("configure_auth0_fastapi_on_app: app.state unwriteable")


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


__all__ = [
    "configure_auth0_fastapi_on_app",
    "get_auth0_fastapi",
    "reset_auth0_fastapi",
]
