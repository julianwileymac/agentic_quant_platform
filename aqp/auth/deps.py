"""FastAPI dependencies — the request-scoped seam for tenancy.

Use these in every new route, and migrate existing routes incrementally:

.. code-block:: python

    from fastapi import Depends
    from aqp.auth import current_context, require_workspace
    from aqp.auth.context import RequestContext

    @router.get("/strategies")
    def list_strategies(
        ctx: RequestContext = Depends(current_context),
        ws_id: str = Depends(require_workspace),
    ):
        ...

The deps respect three optional headers:

- ``X-AQP-User`` — bypass identity resolution for service-to-service calls
  (only honoured when ``settings.auth_provider == "local"``).
- ``X-AQP-Workspace`` — pin the active workspace.
- ``X-AQP-Project`` / ``X-AQP-Lab`` — pin the active project / lab.

Without those headers the dep returns the local-first default context.
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import Depends, Header, HTTPException, status

from aqp.auth.context import RequestContext, default_context, scope_id_for
from aqp.auth.user import (
    CurrentUser,
    accessible_labs,
    accessible_projects,
    accessible_workspaces,
    default_user,
    resolve_user,
    user_can,
)
from aqp.config.defaults import (
    DEFAULT_ORG_ID,
    SCOPE_LAB,
    SCOPE_ORG,
    SCOPE_PROJECT,
    SCOPE_TEAM,
    SCOPE_WORKSPACE,
)

logger = logging.getLogger(__name__)


def current_user(
    x_aqp_user: str | None = Header(default=None, alias="X-AQP-User"),
) -> CurrentUser:
    """Resolve the current user.

    Today: returns the local default unless ``X-AQP-User`` is set to a
    known user id (admin / service-to-service paths can use that header
    when ``auth_provider == "local"``). Wire OIDC by replacing the body
    of :func:`aqp.auth.user.resolve_user`.
    """
    try:
        from aqp.config import settings

        provider = settings.auth_provider
    except Exception:
        provider = "local"

    if provider != "local":
        # OIDC / JWT path is wired here when the platform adopts SSO. For now
        # we reject explicit X-AQP-User headers under non-local providers so
        # impersonation isn't a privilege-escalation hole.
        return resolve_user(fallback_to_default=True)

    if x_aqp_user:
        return resolve_user(user_id=x_aqp_user, fallback_to_default=True)
    return default_user()


def _first_scope_membership(user: CurrentUser, scope_kind: str) -> str | None:
    for membership in user.memberships:
        if membership.get("scope_kind") != scope_kind:
            continue
        scope_id = membership.get("scope_id")
        if isinstance(scope_id, str) and scope_id:
            return scope_id
    return None


def _org_for_workspace(workspace_id: str | None) -> str | None:
    if not workspace_id:
        return None
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Workspace

        with get_session() as session:
            row = (
                session.query(Workspace.org_id)
                .filter(Workspace.id == workspace_id)
                .one_or_none()
            )
            if row is None:
                return None
            return str(row[0]) if row[0] else None
    except Exception:
        logger.debug("Could not derive org_id from workspace_id=%s", workspace_id, exc_info=True)
        return None


def current_context(
    user: CurrentUser = Depends(current_user),
    x_aqp_workspace: str | None = Header(default=None, alias="X-AQP-Workspace"),
    x_aqp_project: str | None = Header(default=None, alias="X-AQP-Project"),
    x_aqp_lab: str | None = Header(default=None, alias="X-AQP-Lab"),
) -> RequestContext:
    """Build a :class:`RequestContext` from the resolved user + headers.

    Validates that the user can access the requested workspace/project/lab.
    Falls back to the user's home context when no headers are provided.
    """
    if user.is_default:
        ctx = default_context()
    else:
        ws_ids = accessible_workspaces(user)
        project_ids = accessible_projects(user)
        lab_ids = accessible_labs(user)
        workspace_id = ws_ids[0] if ws_ids else None
        org_id = (
            _first_scope_membership(user, SCOPE_ORG)
            or _org_for_workspace(workspace_id)
            or DEFAULT_ORG_ID
        )
        ctx = RequestContext(
            user_id=user.id,
            org_id=org_id,
            team_id=_first_scope_membership(user, SCOPE_TEAM),
            workspace_id=workspace_id,
            project_id=project_ids[0] if project_ids else None,
            lab_id=lab_ids[0] if lab_ids else None,
        )

    overrides: dict[str, object] = {}
    if x_aqp_workspace:
        if not user.is_default and not user_can(
            user, "viewer", scope_kind=SCOPE_WORKSPACE, scope_id=x_aqp_workspace
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not a member of workspace {x_aqp_workspace}",
            )
        overrides["workspace_id"] = x_aqp_workspace
        overrides["project_id"] = None
        overrides["lab_id"] = None

    if x_aqp_project:
        if not user.is_default and not user_can(
            user, "viewer", scope_kind=SCOPE_PROJECT, scope_id=x_aqp_project
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot access project {x_aqp_project}",
            )
        overrides["project_id"] = x_aqp_project

    if x_aqp_lab:
        if not user.is_default and not user_can(
            user, "viewer", scope_kind=SCOPE_LAB, scope_id=x_aqp_lab
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot access lab {x_aqp_lab}",
            )
        overrides["lab_id"] = x_aqp_lab

    return ctx.with_overrides(**overrides) if overrides else ctx


# ---------------------------------------------------------------------------
# Convenience dependencies for "this route requires X" guards
# ---------------------------------------------------------------------------
def require_workspace(ctx: RequestContext = Depends(current_context)) -> str:
    """Dep that returns the active workspace id, raising 400 if missing."""
    if not ctx.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active workspace required (set X-AQP-Workspace header)",
        )
    return ctx.workspace_id


def require_project(ctx: RequestContext = Depends(current_context)) -> str:
    if not ctx.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active project required (set X-AQP-Project header)",
        )
    return ctx.project_id


def require_lab(ctx: RequestContext = Depends(current_context)) -> str:
    if not ctx.lab_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active lab required (set X-AQP-Lab header)",
        )
    return ctx.lab_id


def require_role(role: str, scope_kind: str) -> Callable[..., RequestContext]:
    """Build a dep that asserts the current user satisfies *role* on the scope.

    Usage:

    .. code-block:: python

        @router.delete("/workspaces/{wid}")
        def delete_workspace(
            wid: str,
            _: RequestContext = Depends(require_role("admin", "workspace")),
        ):
            ...
    """

    def dep(
        user: CurrentUser = Depends(current_user),
        ctx: RequestContext = Depends(current_context),
    ) -> RequestContext:
        scope_id = scope_id_for(ctx, scope_kind)
        if scope_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Active {scope_kind} required for this operation",
            )
        if not user_can(user, role, scope_kind=scope_kind, scope_id=scope_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {role!r} required on {scope_kind} {scope_id}",
            )
        return ctx

    return dep


__all__ = [
    "current_context",
    "current_user",
    "require_lab",
    "require_project",
    "require_role",
    "require_workspace",
]
