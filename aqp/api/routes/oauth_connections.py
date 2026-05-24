"""``/me/oauth-connections`` routes (Workstream D).

User-facing surface for the external-OAuth wizard:

- ``GET /me/oauth-connections`` — list the user's active +
  recently-revoked connections.
- ``POST /me/oauth-connections/{source}/start`` — kick off the PKCE
  authorize flow; returns the provider's authorize URL + state.
- ``POST /me/oauth-connections/{source}/callback`` — redeem the auth
  code and persist the encrypted token.
- ``DELETE /me/oauth-connections/{id}`` — revoke a connection.
- ``GET /me/oauth-connections/providers`` — list registered
  :class:`ExternalOAuthProvider` slugs for the frontend wizard.

All routes carry the standard :func:`require_authenticated` dep and
honour ``settings.user_oauth_enabled``. The PUBLIC_ROUTERS allowlist
in :mod:`aqp.api.security` is NOT extended — every endpoint here is
strictly user-authenticated.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
from aqp.api.security_stepup import require_step_up
from aqp.auth import CurrentUser, current_user

logger = logging.getLogger(__name__)


router = secure_router(prefix="/me/oauth-connections", tags=["oauth-connections"])


# ---------------------------------------------------------------------------
# Pydantic shapes
# ---------------------------------------------------------------------------


class StartFlowIn(BaseModel):
    redirect_uri: str = Field(description="Where the provider returns the user.")
    config_overrides: dict[str, Any] | None = Field(default=None)


class CallbackIn(BaseModel):
    state: str
    code: str


# ---------------------------------------------------------------------------
# Connection list / providers list
# ---------------------------------------------------------------------------


@router.get("/")
def list_connections(
    user: CurrentUser = Depends(current_user),
) -> dict[str, Any]:
    """Return the active connections for the calling user."""
    _require_feature()
    rows = _list_active_for_user(user.id)
    return {"ok": True, "connections": rows}


@router.get("/providers")
def list_providers() -> dict[str, Any]:
    """Return the registered :class:`ExternalOAuthProvider` slugs."""
    _require_feature()
    from aqp.auth.external_oauth import list_external_oauth_providers

    out = []
    for slug, cls in list_external_oauth_providers().items():
        out.append(
            {
                "slug": slug,
                "display_name": getattr(cls, "display_name", slug),
                "default_scope": getattr(cls, "default_scope", ""),
            }
        )
    return {"ok": True, "providers": out}


# ---------------------------------------------------------------------------
# Authorize flow
# ---------------------------------------------------------------------------


@router.post("/{source}/start")
def start_flow(
    source: str,
    body: StartFlowIn,
    user: CurrentUser = Depends(current_user),
) -> dict[str, Any]:
    _require_feature()
    from aqp.auth.external_oauth.flow import start_authorize_flow
    from aqp.auth.external_oauth.protocol import ExternalOAuthProviderError

    try:
        result = start_authorize_flow(
            user_id=user.id,
            organization_id=_active_org_id(user),
            source=source,
            redirect_uri=body.redirect_uri,
            config_overrides=body.config_overrides,
        )
    except ExternalOAuthProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, **result}


@router.post("/{source}/callback")
def callback(
    source: str,
    body: CallbackIn,
    user: CurrentUser = Depends(current_user),
) -> dict[str, Any]:
    """Complete the PKCE flow.

    ``source`` is the URL slug; it MUST match the state-stashed source.
    """
    _require_feature()
    from aqp.auth.external_oauth.flow import complete_authorize_flow
    from aqp.auth.external_oauth.protocol import ExternalOAuthProviderError

    try:
        row = complete_authorize_flow(state=body.state, code=body.code)
    except ExternalOAuthProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if row.get("source") != source:
        raise HTTPException(
            status_code=400,
            detail="oauth state source mismatch (CSRF protection)",
        )
    return {"ok": True, "connection": row}


@router.delete("/{connection_id}")
def revoke(
    connection_id: str,
    user: CurrentUser = Depends(current_user),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> dict[str, Any]:
    _require_feature()
    from aqp.persistence.db import get_session
    from aqp.persistence.models_oauth_tokens import UserOAuthToken

    with get_session() as session:
        row = (
            session.query(UserOAuthToken)
            .filter(
                UserOAuthToken.id == connection_id,
                UserOAuthToken.user_id == user.id,
            )
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="connection not found")
        row.revoked_at = datetime.utcnow()
        row.revoked_by_user_id = user.id
        session.commit()
        return {"ok": True, "id": str(row.id), "revoked_at": row.revoked_at.isoformat()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_feature() -> None:
    try:
        from aqp.config import settings

        if not bool(getattr(settings, "user_oauth_enabled", False)):
            raise HTTPException(status_code=404, detail="user_oauth_enabled=false")
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        return


def _active_org_id(user: CurrentUser) -> str | None:
    return getattr(user, "organization_id", None) or getattr(user, "org_id", None)


def _list_active_for_user(user_id: str) -> list[dict[str, Any]]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_oauth_tokens import UserOAuthToken

    out: list[dict[str, Any]] = []
    with get_session() as session:
        rows = (
            session.query(UserOAuthToken)
            .filter(UserOAuthToken.user_id == user_id)
            .order_by(UserOAuthToken.created_at.desc())
            .all()
        )
        for row in rows:
            out.append(
                {
                    "id": str(row.id),
                    "source": row.source,
                    "scopes": list(row.scopes or []),
                    "label": row.label,
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                    "last_refreshed_at": (
                        row.last_refreshed_at.isoformat() if row.last_refreshed_at else None
                    ),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                }
            )
    return out


__all__ = ["router"]
