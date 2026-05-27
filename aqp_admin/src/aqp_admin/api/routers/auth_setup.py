"""Auth setup + discovery endpoints for the admin SPA.

Workstream "Entra internal tenant" — exposes the metadata the
Next.js frontend needs to bootstrap its
:class:`@azure/msal-browser.PublicClientApplication` without
hard-coding tenant ids in the frontend bundle.

Two routes:

- ``GET /admin/auth/discovery`` — unauthenticated. Returns the active
  IdP, the issuer / JWKS / authority URLs, the audience the SPA must
  request, and the redirect path. Safe for the frontend to fetch on
  every page load.
- ``GET /admin/auth/health`` — unauthenticated. Verifies the JWKS
  endpoint is reachable + the issuer self-identifies correctly. Used
  by the setup runbook + the CI smoke test.

Both routes return ONLY metadata — no tokens, no client secrets, no
refresh tokens. The frontend never sees secret material; everything
sensitive stays on the server side.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from aqp_admin.deps.identity import _validator_config
from aqp_admin.settings import AdminSettings, get_settings

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/admin/auth", tags=["auth-setup"])


def _provider_kind(settings: AdminSettings) -> str:
    """Active provider — used by the SPA to pick the right SDK."""
    if not settings.auth_enabled:
        return "mock"
    return (settings.auth_provider or "msal_entra").strip().lower()


def _internal_tenant_id(settings: AdminSettings) -> str:
    """The single-tenant id when wired against the AQP staff tenant.

    Empty when running multi-tenant against the ``organizations``
    authority. The frontend treats empty as "use ``organizations``".
    """
    return (settings.auth_msal_internal_tenant_id or "").strip()


def _resolved_audience(settings: AdminSettings) -> str:
    return (
        (settings.auth_msal_internal_audience or "").strip()
        or (settings.auth_oidc_audience or "").strip()
    )


def _frontend_redirect_path(settings: AdminSettings) -> str:
    return (settings.auth_msal_redirect_path or "/api/auth/entra/callback").strip()


def _jwks_uri(issuer: str, override: str = "") -> str:
    if override:
        return override
    return f"{issuer.rstrip('/')}/.well-known/jwks.json"


def _discovery_url(issuer: str) -> str:
    return f"{issuer.rstrip('/')}/.well-known/openid-configuration"


@router.get("/discovery", summary="Public auth discovery for the admin SPA.")
async def auth_discovery(
    settings: AdminSettings = Depends(get_settings),
) -> dict[str, Any]:
    """Return the metadata the admin SPA needs to bootstrap MSAL."""
    provider = _provider_kind(settings)
    if provider == "mock":
        return {
            "provider": "mock",
            "auth_enabled": False,
            "message": (
                "Local sandbox: auth is disabled. The SPA renders an "
                "anonymous user with admin:cluster scope."
            ),
        }

    cfg = _validator_config(settings)
    tenant_id = _internal_tenant_id(settings)
    authority = (
        f"https://login.microsoftonline.com/{tenant_id}"
        if tenant_id
        else f"https://login.microsoftonline.com/{settings.auth_entra_tenant}"
    )
    audience = _resolved_audience(settings)
    return {
        "provider": provider,
        "auth_enabled": True,
        "issuer": cfg.issuer,
        "audience": audience,
        # MSAL scopes follow the ``<audience>/.default`` convention so
        # the staff app gets every role consented at admin-consent time.
        "scopes": [f"{audience}/.default"] if audience else [],
        "jwks_uri": _jwks_uri(cfg.issuer, cfg.jwks_url_override),
        "authority": authority,
        "client_id": (settings.auth_msal_staff_app_id or "").strip(),
        "tenant_id": tenant_id,
        "redirect_path": _frontend_redirect_path(settings),
        "claims_namespace": settings.auth_claims_namespace,
    }


@router.get("/health", summary="Verify the IdP is reachable + self-identifies.")
async def auth_health(
    settings: AdminSettings = Depends(get_settings),
) -> dict[str, Any]:
    """Round-trip the OIDC discovery doc + JWKS endpoint.

    Returns ``ok=True`` only when:

    1. The OpenID configuration document loads.
    2. Its ``issuer`` field matches what the validator expects.
    3. The advertised JWKS endpoint loads and exposes at least one key.

    Used by the setup runbook to confirm the env vars are pointing at a
    real, reachable Entra app.
    """
    if not settings.auth_enabled:
        return {
            "ok": False,
            "auth_enabled": False,
            "reason": "auth is disabled (mock provider). Set AQP_ADMIN_AUTH_REQUIRED=true.",
        }

    cfg = _validator_config(settings)
    discovery_url = _discovery_url(cfg.issuer)
    jwks_uri = _jwks_uri(cfg.issuer, cfg.jwks_url_override)

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            disc = await client.get(discovery_url)
            disc.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "ok": False,
                    "stage": "discovery",
                    "discovery_url": discovery_url,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            ) from exc
        disc_body = disc.json()
        advertised_issuer = str(disc_body.get("issuer") or "").rstrip("/")
        if advertised_issuer != cfg.issuer.rstrip("/"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "ok": False,
                    "stage": "issuer-mismatch",
                    "expected": cfg.issuer,
                    "advertised": advertised_issuer,
                },
            )

        try:
            jwks = await client.get(jwks_uri)
            jwks.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "ok": False,
                    "stage": "jwks",
                    "jwks_uri": jwks_uri,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            ) from exc
        keys = jwks.json().get("keys") or []
        if not keys:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "ok": False,
                    "stage": "jwks-empty",
                    "jwks_uri": jwks_uri,
                },
            )

    return {
        "ok": True,
        "auth_enabled": True,
        "issuer": cfg.issuer,
        "audience": _resolved_audience(settings),
        "jwks_uri": jwks_uri,
        "discovery_url": discovery_url,
        "key_count": len(keys),
    }
