"""Tests for auth dependencies that build request context."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from aqp.auth.user import CurrentUser


def _user(*, memberships: list[dict[str, object]]) -> CurrentUser:
    return CurrentUser(
        id="user-ctx",
        email="ctx@example.com",
        display_name="Ctx User",
        memberships=memberships,
        is_default=False,
    )


def test_current_context_derives_scopes_from_memberships(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.auth import deps

    monkeypatch.setattr(deps, "accessible_workspaces", lambda _user: ["ws-1"])
    monkeypatch.setattr(deps, "accessible_projects", lambda _user: ["project-1"])
    monkeypatch.setattr(deps, "accessible_labs", lambda _user: ["lab-1"])

    user = _user(
        memberships=[
            {"scope_kind": "org", "scope_id": "org-1", "role": "owner", "live_control": True},
            {"scope_kind": "team", "scope_id": "team-1", "role": "owner", "live_control": True},
            {"scope_kind": "workspace", "scope_id": "ws-1", "role": "owner", "live_control": True},
        ]
    )
    ctx = deps.current_context(
        user=user,
        x_aqp_workspace=None,
        x_aqp_project=None,
        x_aqp_lab=None,
    )
    assert ctx.user_id == user.id
    assert ctx.org_id == "org-1"
    assert ctx.team_id == "team-1"
    assert ctx.workspace_id == "ws-1"
    assert ctx.project_id == "project-1"
    assert ctx.lab_id == "lab-1"


def test_workspace_override_clears_project_and_lab(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.auth import deps

    monkeypatch.setattr(deps, "accessible_workspaces", lambda _user: ["ws-1"])
    monkeypatch.setattr(deps, "accessible_projects", lambda _user: ["project-1"])
    monkeypatch.setattr(deps, "accessible_labs", lambda _user: ["lab-1"])
    monkeypatch.setattr(deps, "user_can", lambda *args, **kwargs: True)

    user = _user(
        memberships=[
            {"scope_kind": "org", "scope_id": "org-1", "role": "owner", "live_control": True},
            {"scope_kind": "workspace", "scope_id": "ws-1", "role": "owner", "live_control": True},
        ]
    )
    ctx = deps.current_context(
        user=user,
        x_aqp_workspace="ws-2",
        x_aqp_project=None,
        x_aqp_lab=None,
    )
    assert ctx.workspace_id == "ws-2"
    assert ctx.project_id is None
    assert ctx.lab_id is None


def test_workspace_override_requires_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.auth import deps

    monkeypatch.setattr(deps, "accessible_workspaces", lambda _user: ["ws-1"])
    monkeypatch.setattr(deps, "accessible_projects", lambda _user: ["project-1"])
    monkeypatch.setattr(deps, "accessible_labs", lambda _user: ["lab-1"])
    monkeypatch.setattr(deps, "user_can", lambda *args, **kwargs: False)

    user = _user(
        memberships=[
            {"scope_kind": "org", "scope_id": "org-1", "role": "viewer", "live_control": False},
        ]
    )
    with pytest.raises(HTTPException) as exc:
        deps.current_context(
            user=user,
            x_aqp_workspace="ws-denied",
            x_aqp_project=None,
            x_aqp_lab=None,
        )
    assert exc.value.status_code == 403
