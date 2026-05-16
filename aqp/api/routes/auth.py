"""Auth surface — ``/auth/whoami`` plus accessible-scope listings.

When ``settings.auth_provider == "local"``, ``current_user`` resolves to
the deterministic ``default-user`` row from
:ref:`migration 0017 <alembic-0017>`. When OIDC / JWT is wired, the same
``/auth/whoami`` body is returned with the verified ``sub`` claim,
provider, email, display name, and avatar surfaced from the token —
useful for the frontend identity chip and for cluster-side consumers
that need to discover the active user without re-validating the JWT.

The backend supports two SPA login flows:

1. **Bearer-only** (default): the frontend uses ``@auth0/auth0-react``
   to perform code+PKCE in the browser and attaches
   ``Authorization: Bearer`` to every API call. The backend just
   verifies the token.
2. **Backend session** (M3): the frontend redirects to
   :http:get:`/auth/login`; the backend orchestrates the OIDC flow
   itself via :class:`aqp.auth.providers.IdentityProvider`, persists
   the result in an encrypted cookie / Redis session, and issues
   short-lived M2M tokens for downstream services. Activated when the
   SPA flag ``VITE_AUTH_BACKEND_SESSION=true`` is set.

This module exposes:

- ``GET /auth/whoami`` — verified identity + accessible scopes.
- ``GET /auth/context`` — cheap-polling :class:`RequestContext`.
- ``GET /auth/config`` — public OIDC bootstrap for the frontend SDK.
- ``GET /auth/login`` — backend-session redirect to the IdP login URL.
- ``GET /auth/callback`` — IdP redirect handler; mints session cookie.
- ``POST /auth/exchange`` — server-side ``code`` -> token exchange.
- ``POST /auth/logout`` — clear server session and redirect to IdP logout.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
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


# ---------------------------------------------------------------------------
# Cookie names (kept as module-level constants for the SPA + backend to
# stay in sync via /auth/config).
# ---------------------------------------------------------------------------

SESSION_COOKIE = "aqp_session"
LOGIN_TX_COOKIE = "aqp_login_tx"


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
    backend_session_supported: bool = Field(default=False)
    backend_session_login_url: str = Field(default="/auth/login")
    backend_session_logout_url: str = Field(default="/auth/logout")
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

    backend_session = bool(_session_secret())
    cfg = get_oidc_config()
    if cfg is None:
        return AuthConfigResponse(
            provider=provider,
            backend_session_supported=backend_session,
        )
    return AuthConfigResponse(
        provider=provider,
        issuer=cfg.issuer,
        audience=cfg.audience,
        client_id=cfg.client_id or None,
        backend_session_supported=backend_session,
    )


@router.post("/exchange", response_model=ExchangeResponse)
def exchange_code_route(req: ExchangeRequest) -> ExchangeResponse:
    """Server-side ``authorization_code`` -> token exchange.

    Used by SSR / Electron / desktop clients that can hold a
    confidential client secret. SPA deployments use PKCE in the browser
    and never call this route.

    Routed through :class:`aqp.auth.providers.IdentityProvider` so the
    request always uses the discovered ``token_endpoint`` (Auth0 vs
    Keycloak vs generic OIDC differ here) and shares JWKS / discovery
    caches with the rest of the auth layer.
    """
    cfg = get_oidc_config()
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured for this deployment",
        )

    from aqp.auth.providers import IdentityProviderError, get_active_provider

    try:
        provider = get_active_provider()
        tokens = provider.exchange_code(
            code=req.code,
            redirect_uri=req.redirect_uri,
            code_verifier=req.code_verifier or "",
        )
    except IdentityProviderError as exc:
        logger.warning("OIDC code exchange failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC code exchange failed",
        ) from exc

    return ExchangeResponse(
        access_token=tokens.access_token,
        id_token=tokens.id_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        scope=tokens.scope,
    )


# ---------------------------------------------------------------------------
# Backend-session login flow (Milestone 3)
# ---------------------------------------------------------------------------


@router.get("/login")
def login_redirect(
    request: Request,
    redirect_uri: str | None = None,
    return_to: str | None = None,
) -> RedirectResponse:
    """Redirect the browser to the active IdP's authorize URL.

    Stores the PKCE verifier + ``state`` in a short-lived signed cookie
    so :http:get:`/auth/callback` can finalize the exchange without a
    server-side session table.
    """
    cfg = get_oidc_config()
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured; backend-session login is unavailable",
        )

    from aqp.auth.pkce import generate_code_challenge, generate_code_verifier
    from aqp.auth.providers import get_active_provider
    from aqp.auth.session import EncryptedCookieTransactionStore

    cb = redirect_uri or _login_callback(request)
    state = secrets.token_urlsafe(32)
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier)
    provider = get_active_provider()
    auth_url = provider.login_url(
        redirect_uri=cb,
        state=state,
        code_challenge=challenge,
        scope="openid profile email offline_access",
        audience=cfg.audience or None,
    )

    response = RedirectResponse(url=auth_url, status_code=302)
    secret = _session_secret()
    if secret:
        store = EncryptedCookieTransactionStore(secret=secret, cookie_name=LOGIN_TX_COOKIE)
        token = store.set(
            state,
            {
                "code_verifier": verifier,
                "state": state,
                "redirect_uri": cb,
                "return_to": return_to or "",
            },
        )
        response.set_cookie(
            store.cookie_name,
            token,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=600,
        )
    return response


@router.get("/callback")
def login_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle the IdP redirect; mint the session cookie."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"IdP returned error: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state in callback",
        )
    secret = _session_secret()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AQP_AUTH_SESSION_SECRET is required for backend-session login",
        )

    from aqp.auth.providers import IdentityProviderError, get_active_provider
    from aqp.auth.session import (
        EncryptedCookieStateStore,
        EncryptedCookieTransactionStore,
        session_payload_from_tokens,
    )

    tx_store = EncryptedCookieTransactionStore(secret=secret, cookie_name=LOGIN_TX_COOKIE)
    tx_token = request.cookies.get(LOGIN_TX_COOKIE) or ""
    tx_payload = tx_store.get(state, token=tx_token) if tx_token else None
    if not tx_payload or tx_payload.get("state") != state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login transaction cookie missing or invalid",
        )

    try:
        tokens = get_active_provider().exchange_code(
            code=code,
            redirect_uri=str(tx_payload.get("redirect_uri") or _login_callback(request)),
            code_verifier=str(tx_payload.get("code_verifier") or ""),
        )
    except IdentityProviderError as exc:
        logger.warning("backend-session callback exchange failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC code exchange failed",
        ) from exc

    cfg = get_oidc_config()
    audience = (cfg.audience if cfg else "") or "aqp-api"
    payload = session_payload_from_tokens(
        user_claims={"id_token": tokens.id_token},
        access_token=tokens.access_token,
        id_token=tokens.id_token,
        refresh_token=tokens.refresh_token,
        audience=audience,
        expires_in=tokens.expires_in,
        scope=tokens.scope,
    )
    state_store = EncryptedCookieStateStore(secret=secret, cookie_name=SESSION_COOKIE)
    # Use the cookie name as the HKDF salt. The OAuth state cannot be
    # used as the salt because :func:`aqp.auth.deps.current_user` reads
    # the cookie on subsequent requests without access to the original
    # ``state``. Per-session salting is preserved by the OAuth state +
    # nonce already inside the JWE payload.
    session_token = state_store.set(SESSION_COOKIE, payload)
    return_to = str(tx_payload.get("return_to") or "/")
    response = RedirectResponse(url=return_to, status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=int(tokens.expires_in or 3600),
    )
    response.delete_cookie(LOGIN_TX_COOKIE)
    return response


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    return_to: str | None = None,
) -> dict[str, str]:
    """Invalidate any server-managed session artifacts.

    Clears the encrypted-cookie session and returns the IdP logout URL
    so the SPA can redirect the browser. For pure SPA + bearer-token
    deployments this is still safe to call (it just clears nothing).
    """
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(LOGIN_TX_COOKIE)
    cfg = get_oidc_config()
    logout_url = "/"
    if cfg is not None:
        try:
            from aqp.auth.providers import get_active_provider

            logout_url = get_active_provider().logout_url(return_to=return_to)
        except Exception as exc:  # noqa: BLE001 - never fail logout
            logger.debug("logout_url generation failed: %s", exc)
    return {"status": "ok", "logout_url": logout_url}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_secret() -> str:
    try:
        from aqp.config import settings

        return str(getattr(settings, "auth_session_secret", "") or "")
    except Exception:
        return ""


def _login_callback(request: Request) -> str:
    try:
        from aqp.config import settings

        configured = str(getattr(settings, "auth_login_callback", "") or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    base = str(request.base_url).rstrip("/")
    return f"{base}/auth/callback"
