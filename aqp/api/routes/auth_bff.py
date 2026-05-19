"""``/auth/providers`` + ``/auth/refresh`` — Management Engine BFF surface.

The existing :mod:`aqp.api.routes.auth` module already ships
``GET /auth/whoami``, ``GET /auth/config``, ``POST /auth/exchange``,
``GET /auth/login``, ``GET /auth/callback``, and ``POST /auth/logout``.
This module is purely additive — it adds the two endpoints the BFF
flow needs that the original router does not expose:

- ``GET /auth/providers`` — frontend bootstrap; enumerates every
  registered :class:`aqp.auth.providers.IdentityProvider` (Auth0 /
  Entra / Cloudflare Access / Mock) so the SPA can render a provider
  picker when multiple are configured.
- ``POST /auth/refresh`` — server-side ``refresh_token`` ->
  fresh access token. The SPA + Theia BFF flow keeps refresh tokens in
  the encrypted server session cookie and never exposes them to
  ``localStorage``; this endpoint is the only sanctioned refresh
  ingress.

Both routes mount on the same ``/auth`` prefix as the existing
``aqp.api.routes.auth`` router so the frontend client only needs one
base URL.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth", "management-engine"])


class ProviderDescriptor(BaseModel):
    """Public descriptor for a single registered IdentityProvider."""

    alias: str
    kind: str
    issuer: str | None = None
    audience: str | None = None
    has_client_secret: bool = False
    is_active: bool = False


class ProvidersResponse(BaseModel):
    active_provider: str
    providers: list[ProviderDescriptor]


@router.get("/providers", response_model=ProvidersResponse)
def list_providers() -> ProvidersResponse:
    """Enumerate every registered IdentityProvider for the SPA / Theia bootstrap."""
    from aqp.auth.providers import (
        get_active_provider,
        list_provider_classes,
    )

    try:
        active = get_active_provider()
        active_alias = active.provider_alias or active.__class__.__name__
        active_kind = str(active.provider_kind or "")
    except Exception as exc:  # noqa: BLE001
        logger.debug("active provider unavailable: %s", exc)
        active_alias = ""
        active_kind = ""

    items: list[ProviderDescriptor] = []
    for alias, cls in list_provider_classes().items():
        kind = str(getattr(cls, "provider_kind", "") or "")
        items.append(
            ProviderDescriptor(
                alias=alias,
                kind=kind,
                # Don't instantiate — the class's defaults are enough
                # for the SPA bootstrap; the active provider's full
                # config is at GET /auth/config.
                issuer=None,
                audience=None,
                has_client_secret=False,
                is_active=(kind == active_kind),
            )
        )
    return ProvidersResponse(active_provider=active_alias, providers=items)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(
        ...,
        description=(
            "Refresh token to exchange. The Management Engine subagent "
            "rule forbids logging this value; the route NEVER persists "
            "it to audit logs."
        ),
    )


class RefreshResponse(BaseModel):
    access_token: str
    id_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    scope: str | None = None


@router.post("/refresh", response_model=RefreshResponse)
def refresh_token(req: RefreshRequest) -> RefreshResponse:
    """Server-side refresh exchange via the active IdentityProvider.

    Refresh tokens MUST never reach the browser's localStorage — the
    BFF flow stores them in the encrypted ``aqp_session`` cookie. This
    endpoint reads the cookie, delegates to
    :meth:`aqp.auth.providers.IdentityProvider.refresh`, and returns
    the rotated access token (with the new refresh token when the IdP
    rotated it).
    """
    from aqp.auth.providers import (
        IdentityProviderError,
        get_active_provider,
    )

    try:
        tokens = get_active_provider().refresh(req.refresh_token)
    except IdentityProviderError as exc:
        logger.warning("refresh exchange failed (provider=%s)", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh exchange failed",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("refresh exchange unexpected error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="upstream IdP error",
        ) from exc

    return RefreshResponse(
        access_token=tokens.access_token,
        id_token=tokens.id_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        scope=tokens.scope,
    )


__all__ = ["router"]
