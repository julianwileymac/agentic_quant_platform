"""Tests for ``aqp.auth.user`` — identity resolution + role math."""
from __future__ import annotations

from aqp.auth.user import CurrentUser, default_user, user_can
from aqp.config.defaults import (
    DEFAULT_LAB_ID,
    DEFAULT_USER_ID,
    DEFAULT_WORKSPACE_ID,
    ROLE_OWNER,
    ROLE_VIEWER,
    SCOPE_LAB,
    SCOPE_WORKSPACE,
    role_satisfies,
)


def test_default_user_returns_canonical_seed() -> None:
    user = default_user()
    assert user.id == DEFAULT_USER_ID
    assert user.is_default is True
    assert user.auth_provider == "local"


def test_default_user_owns_default_workspace() -> None:
    user = default_user()
    role = user.role_for(SCOPE_WORKSPACE, DEFAULT_WORKSPACE_ID)
    assert role == ROLE_OWNER


def test_default_user_owns_default_lab() -> None:
    user = default_user()
    role = user.role_for(SCOPE_LAB, DEFAULT_LAB_ID)
    assert role == ROLE_OWNER


def test_default_user_can_anything_anywhere() -> None:
    user = default_user()
    # The default user is always allowed (single-tenant fallback semantics).
    assert user_can(user, ROLE_OWNER, scope_kind=SCOPE_WORKSPACE, scope_id="any")


def test_role_satisfies_lattice() -> None:
    assert role_satisfies(ROLE_OWNER, ROLE_VIEWER)
    assert role_satisfies(ROLE_VIEWER, ROLE_VIEWER)
    assert not role_satisfies(ROLE_VIEWER, ROLE_OWNER)


def test_non_default_user_role_for_returns_strongest_match() -> None:
    user = CurrentUser(
        id="alice",
        email="alice@example.com",
        display_name="Alice",
        memberships=[
            {"scope_kind": SCOPE_WORKSPACE, "scope_id": "ws-1", "role": ROLE_VIEWER, "live_control": False},
            {"scope_kind": SCOPE_WORKSPACE, "scope_id": "ws-1", "role": ROLE_OWNER, "live_control": True},
        ],
    )
    assert user.role_for(SCOPE_WORKSPACE, "ws-1") == ROLE_OWNER


def test_non_default_user_with_only_viewer_cannot_edit() -> None:
    user = CurrentUser(
        id="bob",
        email="bob@example.com",
        display_name="Bob",
        memberships=[
            {"scope_kind": SCOPE_WORKSPACE, "scope_id": "ws-1", "role": ROLE_VIEWER, "live_control": False},
        ],
    )
    assert user_can(user, ROLE_VIEWER, scope_kind=SCOPE_WORKSPACE, scope_id="ws-1")
    assert not user_can(user, "editor", scope_kind=SCOPE_WORKSPACE, scope_id="ws-1")


def test_non_default_user_with_no_membership_is_denied() -> None:
    user = CurrentUser(id="x", email="x@example.com", display_name="X")
    assert not user_can(user, ROLE_VIEWER, scope_kind=SCOPE_WORKSPACE, scope_id="ws-1")
