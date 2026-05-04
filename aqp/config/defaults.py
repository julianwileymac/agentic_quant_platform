"""Deterministic UUIDs and slugs for the default tenancy seed.

The ``0017_tenancy_foundation`` Alembic migration inserts one row per scope
using these IDs. Resource backfill in ``0018_resource_ownership`` copies
:data:`DEFAULT_USER_ID` / :data:`DEFAULT_WORKSPACE_ID` into every legacy row
so a fresh single-tenant deployment continues to work without code changes.

The IDs are intentionally deterministic so:

- Tests can assert against the values directly.
- A second cluster bootstrapped from the same migrations is bit-for-bit
  comparable.
- ``RequestContext.default()`` can synthesise the local-first context with
  zero database round-trips.

Override at runtime via ``AQP_DEFAULT_*_ID`` env vars (handled in
:class:`aqp.config.Settings`). Do not change these constants once a cluster
has been seeded — every legacy row points at them.
"""
from __future__ import annotations

# --- Identity (default org / team / user / workspace / project / lab) ---
DEFAULT_ORG_ID: str = "00000000-0000-0000-0000-000000000001"
DEFAULT_TEAM_ID: str = "00000000-0000-0000-0000-000000000002"
DEFAULT_USER_ID: str = "00000000-0000-0000-0000-000000000003"
DEFAULT_WORKSPACE_ID: str = "00000000-0000-0000-0000-000000000004"
DEFAULT_PROJECT_ID: str = "00000000-0000-0000-0000-000000000005"
DEFAULT_LAB_ID: str = "00000000-0000-0000-0000-000000000006"

# --- Slugs (URL-friendly stable identifiers) ---
DEFAULT_ORG_SLUG: str = "default"
DEFAULT_TEAM_SLUG: str = "default"
DEFAULT_WORKSPACE_SLUG: str = "default"
DEFAULT_PROJECT_SLUG: str = "default"
DEFAULT_LAB_SLUG: str = "default"

# --- Display names ---
DEFAULT_ORG_NAME: str = "Default Organization"
DEFAULT_TEAM_NAME: str = "Default Team"
DEFAULT_WORKSPACE_NAME: str = "Default Workspace"
DEFAULT_PROJECT_NAME: str = "Default Project"
DEFAULT_LAB_NAME: str = "Default Lab"

# --- Default user identity ---
DEFAULT_USER_EMAIL: str = "local@aqp.dev"
DEFAULT_USER_DISPLAY_NAME: str = "Local User"
DEFAULT_USER_AUTH_SUBJECT: str = "local"

# --- Scope kind enum (used by Membership and ConfigOverlayRow) ---
SCOPE_GLOBAL: str = "global"
SCOPE_ORG: str = "org"
SCOPE_TEAM: str = "team"
SCOPE_USER: str = "user"
SCOPE_WORKSPACE: str = "workspace"
SCOPE_PROJECT: str = "project"
SCOPE_LAB: str = "lab"

ALL_SCOPE_KINDS: tuple[str, ...] = (
    SCOPE_GLOBAL,
    SCOPE_ORG,
    SCOPE_TEAM,
    SCOPE_USER,
    SCOPE_WORKSPACE,
    SCOPE_PROJECT,
    SCOPE_LAB,
)

# Resolution order — lowest-precedence first, highest last. The right-hand
# value wins on conflict, mirroring vbt-pro's ``merge_dicts`` semantics.
SCOPE_RESOLUTION_ORDER: tuple[str, ...] = (
    SCOPE_GLOBAL,
    SCOPE_ORG,
    SCOPE_TEAM,
    SCOPE_USER,
    SCOPE_WORKSPACE,
    SCOPE_PROJECT,
)

# --- Roles (viewer < editor < admin < owner) ---
ROLE_VIEWER: str = "viewer"
ROLE_EDITOR: str = "editor"
ROLE_ADMIN: str = "admin"
ROLE_OWNER: str = "owner"

ROLE_RANK: dict[str, int] = {
    ROLE_VIEWER: 1,
    ROLE_EDITOR: 2,
    ROLE_ADMIN: 3,
    ROLE_OWNER: 4,
}

ALL_ROLES: tuple[str, ...] = (ROLE_VIEWER, ROLE_EDITOR, ROLE_ADMIN, ROLE_OWNER)


def role_satisfies(actual: str, required: str) -> bool:
    """Return True iff *actual* meets or exceeds *required* in the role lattice."""
    return ROLE_RANK.get(actual, 0) >= ROLE_RANK.get(required, 0)


__all__ = [
    "ALL_ROLES",
    "ALL_SCOPE_KINDS",
    "DEFAULT_LAB_ID",
    "DEFAULT_LAB_NAME",
    "DEFAULT_LAB_SLUG",
    "DEFAULT_ORG_ID",
    "DEFAULT_ORG_NAME",
    "DEFAULT_ORG_SLUG",
    "DEFAULT_PROJECT_ID",
    "DEFAULT_PROJECT_NAME",
    "DEFAULT_PROJECT_SLUG",
    "DEFAULT_TEAM_ID",
    "DEFAULT_TEAM_NAME",
    "DEFAULT_TEAM_SLUG",
    "DEFAULT_USER_AUTH_SUBJECT",
    "DEFAULT_USER_DISPLAY_NAME",
    "DEFAULT_USER_EMAIL",
    "DEFAULT_USER_ID",
    "DEFAULT_WORKSPACE_ID",
    "DEFAULT_WORKSPACE_NAME",
    "DEFAULT_WORKSPACE_SLUG",
    "ROLE_ADMIN",
    "ROLE_EDITOR",
    "ROLE_OWNER",
    "ROLE_RANK",
    "ROLE_VIEWER",
    "SCOPE_GLOBAL",
    "SCOPE_LAB",
    "SCOPE_ORG",
    "SCOPE_PROJECT",
    "SCOPE_RESOLUTION_ORDER",
    "SCOPE_TEAM",
    "SCOPE_USER",
    "SCOPE_WORKSPACE",
    "role_satisfies",
]
