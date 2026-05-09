"""Tenancy-aware authentication primitives.

Public surface:

- :class:`CurrentUser` — resolved identity for one request/task.
- :class:`RequestContext` — Lean-style ``AlgorithmNodePacket`` carrying the
  active org/team/user/workspace/project/lab/run for any chokepoint that
  needs to stamp ownership.
- :func:`resolve_user` — the auth provider's user-resolution adapter
  (``local`` by default; pluggable for OIDC/JWT later).
- :func:`resolve_context` — combine resolved user + headers into a
  :class:`RequestContext`.
- FastAPI deps: :func:`current_user`, :func:`current_context`,
  :func:`require_workspace`, :func:`require_project`, :func:`require_lab`,
  :func:`require_role`.

Always import the deps via this top-level package so the auth provider
swap-out happens in one place.
"""
from __future__ import annotations

from aqp.auth.context import RequestContext, default_context, scope_id_for
from aqp.auth.contextvars import (
    bind_context,
    current_request_context,
    get_context_or_default,
    use_context,
)
from aqp.auth.deps import (
    current_context,
    current_user,
    require_authenticated,
    require_lab,
    require_project,
    require_role,
    require_workspace,
)
from aqp.auth.user import (
    CurrentUser,
    accessible_labs,
    accessible_projects,
    accessible_workspaces,
    default_user,
    effective_role,
    provision_user_from_claims,
    resolve_user,
    user_can,
)

__all__ = [
    "CurrentUser",
    "RequestContext",
    "accessible_labs",
    "accessible_projects",
    "accessible_workspaces",
    "bind_context",
    "current_context",
    "current_request_context",
    "current_user",
    "default_context",
    "default_user",
    "effective_role",
    "get_context_or_default",
    "provision_user_from_claims",
    "require_authenticated",
    "require_lab",
    "require_project",
    "require_role",
    "require_workspace",
    "resolve_user",
    "scope_id_for",
    "use_context",
    "user_can",
]
