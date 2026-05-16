"""FastAPI auth enforcement primitives — Phase 4 of the multi-tenant rollout.

Three layers, all built on top of :mod:`aqp.auth.deps`:

- :func:`require_authenticated` — drop-in re-export so route files
  don't need a second import.
- :func:`require_scope` — JWT scope / permissions / custom-claim
  enforcement. Reads ``scope`` (OAuth standard), ``permissions``
  (Auth0 RBAC array), and the AQP-namespaced ``https://aqp/roles``
  custom claim.
- :func:`require_membership` — Postgres-backed RBAC. Asserts the
  current user has at least ``min_role`` on the active scope
  (workspace / project / lab / team / org).

The :func:`secure_router` helper wraps :class:`fastapi.APIRouter` so a
route module opts in to "every endpoint requires auth" with one line.
The rollout sweep replaces ``router = APIRouter(...)`` with
``router = secure_router(...)`` on each module that isn't on the
:data:`PUBLIC_ROUTERS` allowlist.

Enforcement mode (``AQP_AUTH_ENFORCE``):

- ``strict`` (default in production): 401/403 on every violation.
- ``permissive``: logs the violation + emits an OTEL span attribute
  but still allows the request through. Used during the rollout so
  the dashboard can show every would-be denial before the cut-over.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status

from aqp.auth import (
    CurrentUser,
    RequestContext,
    current_context,
    current_user,
    require_authenticated as _require_authenticated_base,
)
from aqp.auth.user import user_can
from aqp.config import settings
from aqp.config.defaults import (
    SCOPE_LAB,
    SCOPE_ORG,
    SCOPE_PROJECT,
    SCOPE_TEAM,
    SCOPE_WORKSPACE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bypass allowlist
# ---------------------------------------------------------------------------

# Routes that intentionally accept unauthenticated traffic. New
# entries require an explicit code review note explaining why.
PUBLIC_ROUTERS: frozenset[str] = frozenset(
    {
        "health",          # cluster + k8s probes
        "auth",            # /auth/login + /auth/callback + /auth/config
        "monitoring",      # node exporter scrape
    }
)


# ---------------------------------------------------------------------------
# Enforcement mode
# ---------------------------------------------------------------------------


def _is_strict() -> bool:
    mode = str(getattr(settings, "auth_enforce", "strict") or "strict").lower()
    return mode == "strict"


def _violation(
    *,
    code: int,
    detail: str,
    request: Request | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """Either raise (strict) or log + tag the OTEL span (permissive)."""
    if _is_strict():
        raise HTTPException(status_code=code, detail=detail, headers=headers or {})
    logger.warning(
        "auth.violation code=%s detail=%r path=%s",
        code,
        detail,
        getattr(request, "url", None) if request else None,
    )
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]

        span = trace.get_current_span()
        if span is not None and span.is_recording():
            span.set_attribute("aqp.auth.would_deny", True)
            span.set_attribute("aqp.auth.would_deny_code", code)
            span.set_attribute("aqp.auth.would_deny_detail", detail)
    except Exception:  # pragma: no cover - OTEL optional
        return


# ---------------------------------------------------------------------------
# require_authenticated
# ---------------------------------------------------------------------------


def require_authenticated(
    user: CurrentUser = Depends(current_user),
    request: Request = None,  # type: ignore[assignment]
) -> CurrentUser:
    """Reject unauthenticated traffic (strict) or log it (permissive).

    Drop-in replacement for :func:`aqp.auth.deps.require_authenticated`
    that honours :attr:`Settings.auth_enforce`.
    """
    try:
        return _require_authenticated_base(user)
    except HTTPException as exc:
        if _is_strict():
            raise
        logger.warning(
            "auth.violation status=%s detail=%r path=%s",
            exc.status_code,
            exc.detail,
            getattr(request, "url", None) if request else None,
        )
        return user


# ---------------------------------------------------------------------------
# require_scope
# ---------------------------------------------------------------------------


def _granted_scopes_for(user: CurrentUser, request: Request | None) -> set[str]:
    """Best-effort union of JWT-derived and DB-derived scopes.

    - OAuth standard ``scope`` claim (space-separated string).
    - Auth0 RBAC ``permissions`` claim (array of strings).
    - AQP-namespaced custom claim ``https://aqp/scopes`` (array).
    - AQP-namespaced custom claim ``https://aqp/roles`` (array) is
      expanded to ``data:read`` / ``data:write`` / ``admin``.
    - Local-default users get ``data:read`` + ``data:write`` so the
      local dev loop keeps working.
    """
    scopes: set[str] = set()
    if request is not None:
        claims = getattr(request.state, "oidc_claims", None)
        if isinstance(claims, dict):
            scope_str = claims.get("scope")
            if isinstance(scope_str, str):
                scopes.update(scope_str.split())
            for arr_key in ("permissions", "scopes", "https://aqp/scopes"):
                arr = claims.get(arr_key)
                if isinstance(arr, list):
                    scopes.update(str(s) for s in arr if isinstance(s, str))
            roles = claims.get("https://aqp/roles")
            if isinstance(roles, list):
                for role in roles:
                    role_str = str(role).lower()
                    if role_str in ("admin", "owner"):
                        scopes.update({"data:read", "data:write", "admin"})
                    elif role_str == "editor":
                        scopes.update({"data:read", "data:write"})
                    elif role_str == "viewer":
                        scopes.add("data:read")
    if user.is_default:
        # Local-first dev never has an Authorization header; treat the
        # default user as fully scoped so existing test fixtures keep
        # passing. Production deploys gate this by setting
        # ``AQP_AUTH_PROVIDER=auth0`` so the default user can't exist.
        scopes.update({"data:read", "data:write"})
    return scopes


def require_scope(*required: str) -> Callable[..., CurrentUser]:
    """Build a dep that asserts every scope in *required* is granted.

    Example::

        @router.post("/datasets/upload")
        async def upload(
            payload: UploadIn,
            user: CurrentUser = Depends(require_scope("data:write")),
        ):
            ...
    """
    required_set = tuple(required)

    def _dep(
        request: Request,
        user: CurrentUser = Depends(require_authenticated),
    ) -> CurrentUser:
        granted = _granted_scopes_for(user, request)
        missing = [s for s in required_set if s not in granted]
        if missing:
            _violation(
                code=status.HTTP_403_FORBIDDEN,
                detail=f"missing scope(s): {missing}",
                request=request,
            )
        return user

    return _dep


# ---------------------------------------------------------------------------
# require_membership
# ---------------------------------------------------------------------------


_SCOPE_KEY_MAP: dict[str, str] = {
    "org": SCOPE_ORG,
    "team": SCOPE_TEAM,
    "workspace": SCOPE_WORKSPACE,
    "project": SCOPE_PROJECT,
    "lab": SCOPE_LAB,
}


def require_membership(
    min_role: str = "viewer",
    scope: str = "workspace",
) -> Callable[..., RequestContext]:
    """Dep that asserts ``user_can(user, min_role, scope_kind=scope, scope_id=ctx.<scope>_id)``.

    The ``scope`` argument picks which id on :class:`RequestContext` is
    checked. Common values:

    - ``"org"``: checks ``ctx.org_id``.
    - ``"team"``: checks ``ctx.team_id``.
    - ``"workspace"`` (default): checks ``ctx.workspace_id``.
    - ``"project"``: checks ``ctx.project_id``.
    - ``"lab"``: checks ``ctx.lab_id``.
    """
    scope_kind = _SCOPE_KEY_MAP.get(scope.lower(), SCOPE_WORKSPACE)

    def _dep(
        request: Request,
        user: CurrentUser = Depends(require_authenticated),
        ctx: RequestContext = Depends(current_context),
    ) -> RequestContext:
        from aqp.auth.context import scope_id_for

        scope_id = scope_id_for(ctx, scope_kind)
        if not scope_id:
            _violation(
                code=status.HTTP_400_BAD_REQUEST,
                detail=f"active {scope} required for this operation",
                request=request,
            )
            return ctx
        if not user_can(
            user, min_role, scope_kind=scope_kind, scope_id=scope_id
        ):
            _violation(
                code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"role {min_role!r} required on {scope} {scope_id} "
                    f"(current memberships: "
                    f"{[m.get('role') for m in user.memberships]})"
                ),
                request=request,
            )
        return ctx

    return _dep


# ---------------------------------------------------------------------------
# secure_router
# ---------------------------------------------------------------------------


def secure_router(
    *,
    prefix: str = "",
    tags: list[str] | None = None,
    default_scope: str | None = None,
    extra_dependencies: list[Any] | None = None,
) -> APIRouter:
    """Build an :class:`APIRouter` with a default ``require_authenticated`` dep.

    Optional ``default_scope`` chains a :func:`require_scope` check
    onto every route. ``extra_dependencies`` lets a module add more
    deps without losing the default ones (e.g. an OTEL span tag).
    """
    deps: list[Any] = [Depends(require_authenticated)]
    if default_scope:
        deps.append(Depends(require_scope(default_scope)))
    if extra_dependencies:
        deps.extend(extra_dependencies)
    return APIRouter(
        prefix=prefix,
        tags=tags or [],
        dependencies=deps,
    )


__all__ = [
    "PUBLIC_ROUTERS",
    "require_authenticated",
    "require_membership",
    "require_scope",
    "secure_router",
]
