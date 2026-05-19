"""Four-role RBAC scope grid (ADR 003).

Roles compose by including all scopes of the next-lower role:

| Role                | Scopes                                                       |
| ------------------- | ------------------------------------------------------------ |
| ``aqp-viewer``      | ``read:infrastructure``                                       |
| ``aqp-operator``    | viewer + ``manage:agents``                                    |
| ``aqp-admin``       | operator + ``manage:infrastructure``                          |
| ``aqp-superadmin``  | admin + ``admin:cluster`` (the only role that bypasses        |
|                     | :func:`aqp_platform_core.auth.resource_filter.filter_resources`)|
"""
from __future__ import annotations

# --- Scopes ----------------------------------------------------------------

SCOPE_READ_INFRA = "read:infrastructure"
SCOPE_MANAGE_AGENTS = "manage:agents"
SCOPE_MANAGE_INFRA = "manage:infrastructure"
SCOPE_ADMIN_CLUSTER = "admin:cluster"

ALL_SCOPES: frozenset[str] = frozenset(
    {
        SCOPE_READ_INFRA,
        SCOPE_MANAGE_AGENTS,
        SCOPE_MANAGE_INFRA,
        SCOPE_ADMIN_CLUSTER,
    }
)

# --- Roles ----------------------------------------------------------------

ROLE_VIEWER = "aqp-viewer"
ROLE_OPERATOR = "aqp-operator"
ROLE_ADMIN = "aqp-admin"
ROLE_SUPERADMIN = "aqp-superadmin"

_ROLE_LATTICE: dict[str, frozenset[str]] = {
    ROLE_VIEWER: frozenset({SCOPE_READ_INFRA}),
    ROLE_OPERATOR: frozenset({SCOPE_READ_INFRA, SCOPE_MANAGE_AGENTS}),
    ROLE_ADMIN: frozenset(
        {SCOPE_READ_INFRA, SCOPE_MANAGE_AGENTS, SCOPE_MANAGE_INFRA}
    ),
    ROLE_SUPERADMIN: frozenset(
        {
            SCOPE_READ_INFRA,
            SCOPE_MANAGE_AGENTS,
            SCOPE_MANAGE_INFRA,
            SCOPE_ADMIN_CLUSTER,
        }
    ),
}


def expand_role(role: str) -> frozenset[str]:
    """Return the set of scopes implied by ``role``. Unknown -> empty set."""
    return _ROLE_LATTICE.get(role, frozenset())


def role_grants(role: str, scope: str) -> bool:
    """Return ``True`` if ``role`` implies ``scope``."""
    return scope in expand_role(role)


__all__ = [
    "SCOPE_READ_INFRA",
    "SCOPE_MANAGE_AGENTS",
    "SCOPE_MANAGE_INFRA",
    "SCOPE_ADMIN_CLUSTER",
    "ALL_SCOPES",
    "ROLE_VIEWER",
    "ROLE_OPERATOR",
    "ROLE_ADMIN",
    "ROLE_SUPERADMIN",
    "expand_role",
    "role_grants",
]
