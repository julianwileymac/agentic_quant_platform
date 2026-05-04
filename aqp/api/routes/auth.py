"""Auth surface — ``/auth/whoami`` plus accessible-scope listings.

The platform is local-first today: ``current_user`` resolves to the
deterministic ``default-user`` row from
:ref:`migration 0017 <alembic-0017>`. When OIDC / JWT lands, this module
gains ``/auth/login``, ``/auth/refresh``, ``/auth/logout``; the route
shapes already match the eventual SSO response, so the webui's identity
chip can be wired today and re-used unchanged.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from aqp.auth import (
    CurrentUser,
    RequestContext,
    accessible_labs,
    accessible_projects,
    accessible_workspaces,
    current_context,
    current_user,
)

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
    workspaces: list[ScopeRef] = []
    projects: list[ScopeRef] = []
    labs: list[ScopeRef] = []
    active_context: dict[str, Any] = {}


@router.get("/whoami", response_model=WhoAmI)
def whoami(
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
    return WhoAmI(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        auth_provider=user.auth_provider,
        auth_subject=user.auth_subject,
        is_default=user.is_default,
        workspaces=workspaces,
        projects=projects,
        labs=labs,
        active_context=ctx.to_dict(),
    )


@router.get("/context")
def context(ctx: RequestContext = Depends(current_context)) -> dict[str, Any]:
    """Return just the active :class:`RequestContext` (cheap polling target)."""
    return ctx.to_dict()
