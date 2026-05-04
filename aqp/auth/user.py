"""User identity resolution + accessibility queries.

This module is the single seam between the rest of AQP and *who* is making
a request. Today the default ``auth_provider="local"`` returns the
deterministic ``default-user`` row from
:ref:`migration 0017 <alembic-0017>`. When the platform is wired to OIDC,
swap :func:`resolve_user` to a JWT-validating implementation; everything
else (the FastAPI deps, the chokepoints, the UI) keeps working unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aqp.config.defaults import (
    DEFAULT_LAB_ID,
    DEFAULT_ORG_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_TEAM_ID,
    DEFAULT_USER_DISPLAY_NAME,
    DEFAULT_USER_EMAIL,
    DEFAULT_USER_ID,
    DEFAULT_WORKSPACE_ID,
    ROLE_OWNER,
    ROLE_RANK,
    SCOPE_LAB,
    SCOPE_ORG,
    SCOPE_PROJECT,
    SCOPE_TEAM,
    SCOPE_WORKSPACE,
    role_satisfies,
)

logger = logging.getLogger(__name__)


@dataclass
class CurrentUser:
    """Resolved identity for one request/task.

    The ``memberships`` field is the cached list of Membership rows for
    this user; the deps reuse it to avoid round-trip-per-check storms when
    a single request touches multiple resources.
    """

    id: str
    email: str
    display_name: str
    auth_provider: str = "local"
    auth_subject: str | None = None
    status: str = "active"
    memberships: list[dict[str, Any]] = field(default_factory=list)
    is_default: bool = False

    def role_for(self, scope_kind: str, scope_id: str) -> str | None:
        """Return the strongest role this user has on the given scope."""
        ranked = [
            m["role"]
            for m in self.memberships
            if m.get("scope_kind") == scope_kind
            and m.get("scope_id") == scope_id
        ]
        if not ranked:
            return None
        return max(ranked, key=lambda r: ROLE_RANK.get(r, 0))


def default_user() -> CurrentUser:
    """Synthesise the local-first default user without touching Postgres."""
    return CurrentUser(
        id=DEFAULT_USER_ID,
        email=DEFAULT_USER_EMAIL,
        display_name=DEFAULT_USER_DISPLAY_NAME,
        auth_provider="local",
        auth_subject="local",
        status="active",
        memberships=[
            {"scope_kind": SCOPE_ORG, "scope_id": DEFAULT_ORG_ID, "role": ROLE_OWNER, "live_control": True},
            {"scope_kind": SCOPE_TEAM, "scope_id": DEFAULT_TEAM_ID, "role": ROLE_OWNER, "live_control": True},
            {"scope_kind": SCOPE_WORKSPACE, "scope_id": DEFAULT_WORKSPACE_ID, "role": ROLE_OWNER, "live_control": True},
            {"scope_kind": SCOPE_PROJECT, "scope_id": DEFAULT_PROJECT_ID, "role": ROLE_OWNER, "live_control": True},
            {"scope_kind": SCOPE_LAB, "scope_id": DEFAULT_LAB_ID, "role": ROLE_OWNER, "live_control": True},
        ],
        is_default=True,
    )


def _load_user(*, user_id: str | None = None, email: str | None = None, auth_subject: str | None = None) -> CurrentUser | None:
    """Load + hydrate a user (with memberships) from Postgres."""
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Membership, User

        with get_session() as session:
            q = session.query(User)
            if user_id:
                q = q.filter(User.id == user_id)
            elif email:
                q = q.filter(User.email == email)
            elif auth_subject:
                q = q.filter(User.auth_subject == auth_subject)
            else:
                return None
            row = q.one_or_none()
            if row is None:
                return None
            memberships = (
                session.query(Membership)
                .filter(Membership.user_id == row.id)
                .all()
            )
            mlist = [
                {
                    "scope_kind": m.scope_kind,
                    "scope_id": m.scope_id,
                    "role": m.role,
                    "live_control": bool(m.live_control),
                }
                for m in memberships
            ]
            return CurrentUser(
                id=row.id,
                email=row.email,
                display_name=row.display_name,
                auth_provider=row.auth_provider,
                auth_subject=row.auth_subject,
                status=row.status,
                memberships=mlist,
                is_default=(row.id == DEFAULT_USER_ID),
            )
    except Exception:
        logger.debug("User lookup failed", exc_info=True)
        return None


def resolve_user(
    *,
    user_id: str | None = None,
    email: str | None = None,
    auth_subject: str | None = None,
    fallback_to_default: bool = True,
) -> CurrentUser:
    """Resolve a :class:`CurrentUser` from any of the available identifiers.

    Resolution order:

    1. If ``user_id`` matches a row in ``users``, return it.
    2. Else if ``auth_subject`` matches an OIDC-provisioned row, return it.
    3. Else if ``email`` matches, return it.
    4. Else (and ``fallback_to_default``), return :func:`default_user`.

    The OIDC adapter (when added) calls this with the validated ``sub``
    claim; today every code path lands in step (4).
    """
    settings = _settings_safe()
    if user_id and user_id == DEFAULT_USER_ID:
        return default_user()

    user: CurrentUser | None = None
    for kwargs in (
        {"user_id": user_id} if user_id else None,
        {"auth_subject": auth_subject} if auth_subject else None,
        {"email": email} if email else None,
    ):
        if kwargs is None:
            continue
        user = _load_user(**kwargs)
        if user is not None:
            return user

    if not fallback_to_default:
        raise LookupError("Could not resolve user")

    if settings is not None and settings.auth_provider != "local":
        logger.warning(
            "Falling back to default user under auth_provider=%s — "
            "the OIDC adapter probably has not been wired yet",
            settings.auth_provider,
        )
    return default_user()


def _settings_safe():
    try:
        from aqp.config import settings

        return settings
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Accessibility queries — used by the explorer + admin pages
# ---------------------------------------------------------------------------
def accessible_workspaces(user: CurrentUser) -> list[str]:
    """Return the IDs of workspaces this user can see (any role)."""
    return _accessible_ids(user, SCOPE_WORKSPACE)


def accessible_projects(user: CurrentUser) -> list[str]:
    """Return the IDs of projects this user can see (any role)."""
    return _accessible_ids(user, SCOPE_PROJECT)


def accessible_labs(user: CurrentUser) -> list[str]:
    return _accessible_ids(user, SCOPE_LAB)


def _accessible_ids(user: CurrentUser, scope_kind: str) -> list[str]:
    direct = {m["scope_id"] for m in user.memberships if m.get("scope_kind") == scope_kind}
    if scope_kind in (SCOPE_PROJECT, SCOPE_LAB):
        # Anyone with workspace membership inherits read access to its
        # projects/labs (unless workspace.visibility="private" — handled by
        # the API layer when filtering listings).
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_tenancy import Lab, Project

            workspace_ids = {
                m["scope_id"] for m in user.memberships if m.get("scope_kind") == SCOPE_WORKSPACE
            }
            if workspace_ids:
                with get_session() as session:
                    if scope_kind == SCOPE_PROJECT:
                        rows = (
                            session.query(Project.id)
                            .filter(Project.workspace_id.in_(workspace_ids))
                            .all()
                        )
                    else:
                        rows = (
                            session.query(Lab.id)
                            .filter(Lab.workspace_id.in_(workspace_ids))
                            .all()
                        )
                    direct.update(r[0] for r in rows)
        except Exception:
            logger.debug(
                "Could not expand workspace memberships into %s ids", scope_kind, exc_info=True
            )
    return sorted(direct)


def effective_role(user: CurrentUser, scope_kind: str, scope_id: str) -> str | None:
    """Return the strongest role *user* has on the given scope, walking up.

    A user with ``admin`` on a workspace inherits ``admin`` on every project
    and lab inside it (unless explicit grants supersede).
    """
    if user.is_default:
        return ROLE_OWNER

    direct = user.role_for(scope_kind, scope_id)

    parent_role: str | None = None
    if scope_kind in (SCOPE_PROJECT, SCOPE_LAB):
        parent_role = _parent_workspace_role(user, scope_kind, scope_id)
    elif scope_kind == SCOPE_WORKSPACE:
        parent_role = _parent_org_role(user, scope_id)

    candidates = [r for r in (direct, parent_role) if r is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda r: ROLE_RANK.get(r, 0))


def _parent_workspace_role(user: CurrentUser, scope_kind: str, scope_id: str) -> str | None:
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Lab, Project

        with get_session() as session:
            row = None
            if scope_kind == SCOPE_PROJECT:
                row = session.query(Project.workspace_id).filter(Project.id == scope_id).one_or_none()
            else:
                row = session.query(Lab.workspace_id).filter(Lab.id == scope_id).one_or_none()
            if row is None:
                return None
            workspace_id = row[0]
        return user.role_for(SCOPE_WORKSPACE, workspace_id)
    except Exception:
        return None


def _parent_org_role(user: CurrentUser, workspace_id: str) -> str | None:
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Workspace

        with get_session() as session:
            row = session.query(Workspace.org_id).filter(Workspace.id == workspace_id).one_or_none()
            if row is None:
                return None
            org_id = row[0]
        return user.role_for(SCOPE_ORG, org_id)
    except Exception:
        return None


def user_can(
    user: CurrentUser,
    required_role: str,
    *,
    scope_kind: str,
    scope_id: str,
) -> bool:
    """Return True iff *user*'s effective role on the scope satisfies *required_role*."""
    if user.is_default:
        return True
    role = effective_role(user, scope_kind, scope_id)
    if role is None:
        return False
    return role_satisfies(role, required_role)


__all__ = [
    "CurrentUser",
    "accessible_labs",
    "accessible_projects",
    "accessible_workspaces",
    "default_user",
    "effective_role",
    "resolve_user",
    "user_can",
]
