"""Auth surface — ``/auth/whoami`` plus accessible-scope listings.

When ``settings.auth_provider == "local"``, ``current_user`` resolves to
the deterministic ``default-user`` row from
:ref:`migration 0017 <alembic-0017>`. When OIDC / JWT is wired, the same
``/auth/whoami`` body is returned with the verified ``sub`` claim,
provider, email, display name, and avatar surfaced from the token —
useful for the frontend identity chip and for cluster-side consumers
that need to discover the active user without re-validating the JWT.

In OIDC mode the frontend handles the authorization-code-with-PKCE flow
via ``@auth0/auth0-react``; the backend only sees the resulting
``Authorization: Bearer <token>``. This module therefore exposes:

- ``GET /auth/whoami`` — verified identity + accessible scopes.
- ``GET /auth/context`` — cheap-polling :class:`RequestContext`.
- ``GET /auth/config`` — the public OIDC bootstrap (issuer / audience /
  client id) for the frontend SDK; safe to expose since these values
  are also baked into the SPA bundle.
- ``POST /auth/exchange`` — server-side ``code`` -> token exchange for
  SSR / Electron clients that cannot store an SPA client secret. No-op
  when the deployment uses public-client PKCE only.
- ``POST /auth/logout`` — invalidate any server-managed session
  artifacts (none today; reserved for future server-issued cookies).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from aqp.auth import (
    CurrentUser,
    RequestContext,
    accessible_labs,
    accessible_projects,
    accessible_workspaces,
    current_context,
    current_user,
)
from aqp.auth.oidc import claims_picture, get_oidc_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class ScopeRef(BaseModel):
    id: str
    role: str | None = None
    live_control: bool = False


class WhoAmI(BaseModel):
    id: str
    email: str
    display_name: str
    auth_provider: str = "local"
    auth_subject: str | None = None
    is_default: bool = False
    avatar_url: str | None = None
    workspaces: list[ScopeRef] = []
    projects: list[ScopeRef] = []
    labs: list[ScopeRef] = []
    active_context: dict[str, Any] = {}


class AuthConfigResponse(BaseModel):
    """Public OIDC bootstrap payload, safe to ship to the SPA bundle."""

    provider: str = Field(default="local")
    issuer: str | None = None
    audience: str | None = None
    client_id: str | None = None
    workspace_header: str = Field(default="X-AQP-Workspace")
    project_header: str = Field(default="X-AQP-Project")
    lab_header: str = Field(default="X-AQP-Lab")


class ExchangeRequest(BaseModel):
    """Authorization code coming back from the IdP redirect."""

    code: str
    redirect_uri: str
    code_verifier: str | None = None


class ExchangeResponse(BaseModel):
    access_token: str
    id_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    scope: str | None = None


@router.get("/whoami", response_model=WhoAmI)
def whoami(
    request: Request,
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> WhoAmI:
    workspaces = [
        ScopeRef(id=wid, role=user.role_for("workspace", wid))
        for wid in accessible_workspaces(user)
    ]
    projects = [
        ScopeRef(id=pid, role=user.role_for("project", pid))
        for pid in accessible_projects(user)
    ]
    labs = [
        ScopeRef(id=lid, role=user.role_for("lab", lid))
        for lid in accessible_labs(user)
    ]
    avatar_url: str | None = None
    claims = getattr(request.state, "oidc_claims", None)
    if isinstance(claims, dict):
        avatar_url = claims_picture(claims)

    return WhoAmI(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        auth_provider=user.auth_provider,
        auth_subject=user.auth_subject,
        is_default=user.is_default,
        avatar_url=avatar_url,
        workspaces=workspaces,
        projects=projects,
        labs=labs,
        active_context=ctx.to_dict(),
    )


@router.get("/context")
def context(ctx: RequestContext = Depends(current_context)) -> dict[str, Any]:
    """Return just the active :class:`RequestContext` (cheap polling target)."""
    return ctx.to_dict()


@router.get("/config", response_model=AuthConfigResponse)
def auth_config() -> AuthConfigResponse:
    """Public OIDC bootstrap payload for the SPA.

    The frontend reads ``/auth/config`` once at boot to learn which
    issuer / audience / client id the local backend expects. This avoids
    duplicating the values in environment files for both the API and the
    SPA bundle and lets a single deployment serve dev/staging/prod
    without rebuilding the frontend.
    """
    try:
        from aqp.config import settings

        provider = str(settings.auth_provider).lower()
    except Exception:
        provider = "local"

    if provider == "local":
        return AuthConfigResponse(provider="local")

    cfg = get_oidc_config()
    if cfg is None:
        return AuthConfigResponse(provider=provider)
    return AuthConfigResponse(
        provider=provider,
        issuer=cfg.issuer,
        audience=cfg.audience,
        client_id=cfg.client_id or None,
    )


@router.post("/exchange", response_model=ExchangeResponse)
async def exchange_code(req: ExchangeRequest) -> ExchangeResponse:
    """Server-side ``authorization_code`` -> token exchange.

    Used by SSR / Electron / desktop clients that can hold a
    confidential client secret. SPA deployments use PKCE in the browser
    and never call this route.

    The endpoint reads the issuer / client id / audience from
    :func:`get_oidc_config`. The client secret comes from
    ``settings.auth_oidc_client_secret`` if you wire it in; the route
    does not log it.
    """
    try:
        from aqp.config import settings
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"settings unavailable: {exc}") from exc

    cfg = get_oidc_config()
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured for this deployment",
        )

    client_secret = getattr(settings, "auth_oidc_client_secret", "") or ""
    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": req.code,
        "redirect_uri": req.redirect_uri,
        "client_id": cfg.client_id,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    if req.code_verifier:
        payload["code_verifier"] = req.code_verifier
    if cfg.audience:
        payload["audience"] = cfg.audience

    token_url = f"{cfg.issuer.rstrip('/')}/oauth/token"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(token_url, data=payload)
            if response.status_code >= 400:
                logger.warning(
                    "OIDC code exchange failed: status=%s body=%s",
                    response.status_code,
                    response.text[:512],
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="OIDC code exchange failed",
                )
            data = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Token endpoint unreachable: {exc}",
        ) from exc

    return ExchangeResponse(
        access_token=str(data.get("access_token") or ""),
        id_token=data.get("id_token"),
        refresh_token=data.get("refresh_token"),
        token_type=str(data.get("token_type") or "Bearer"),
        expires_in=int(data["expires_in"]) if data.get("expires_in") is not None else None,
        scope=data.get("scope"),
    )


@router.post("/logout")
def logout() -> dict[str, str]:
    """Invalidate any server-managed session artifacts.

    No-op for SPA + bearer-token deployments (the frontend just drops
    the token). Reserved for the future server-issued cookie path.
    """
    return {"status": "ok"}
