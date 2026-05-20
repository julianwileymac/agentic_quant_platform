"""RBAC role lattice tests."""
from __future__ import annotations

from aqp_platform_core.auth import (
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_SUPERADMIN,
    ROLE_VIEWER,
    SCOPE_ADMIN_CLUSTER,
    SCOPE_MANAGE_AGENTS,
    SCOPE_MANAGE_INFRA,
    SCOPE_READ_INFRA,
    expand_role,
    role_grants,
)


def test_viewer_has_only_read_scopes() -> None:
    scopes = expand_role(ROLE_VIEWER)
    assert SCOPE_READ_INFRA in scopes
    assert SCOPE_MANAGE_AGENTS not in scopes
    assert SCOPE_MANAGE_INFRA not in scopes
    assert SCOPE_ADMIN_CLUSTER not in scopes


def test_operator_subsumes_viewer() -> None:
    operator = expand_role(ROLE_OPERATOR)
    viewer = expand_role(ROLE_VIEWER)
    assert viewer <= operator
    assert SCOPE_MANAGE_AGENTS in operator


def test_admin_subsumes_operator() -> None:
    admin = expand_role(ROLE_ADMIN)
    operator = expand_role(ROLE_OPERATOR)
    assert operator <= admin
    assert SCOPE_MANAGE_INFRA in admin
    assert SCOPE_ADMIN_CLUSTER not in admin  # admin:cluster is superadmin-only


def test_superadmin_has_admin_cluster() -> None:
    assert SCOPE_ADMIN_CLUSTER in expand_role(ROLE_SUPERADMIN)


def test_role_grants_helper() -> None:
    assert role_grants(ROLE_ADMIN, SCOPE_MANAGE_INFRA)
    assert not role_grants(ROLE_OPERATOR, SCOPE_MANAGE_INFRA)
    assert not role_grants("unknown-role", SCOPE_READ_INFRA)


def test_unknown_role_returns_empty() -> None:
    assert expand_role("aqp-ghost") == frozenset()
