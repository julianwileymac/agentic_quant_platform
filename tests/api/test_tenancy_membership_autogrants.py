"""Unit tests for tenancy route auto-grant behavior."""
from __future__ import annotations

from datetime import datetime

import pytest

from aqp.auth.user import CurrentUser
from aqp.persistence.models_tenancy import Membership


class _FakeAsyncSession:
    """Tiny async-session double for route-unit tests."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self._next_id = 0

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        for row in self.added:
            if not hasattr(row, "id"):
                continue
            row_id = getattr(row, "id", None)
            if row_id:
                continue
            self._next_id += 1
            setattr(row, "id", f"test-id-{self._next_id}")

    async def commit(self) -> None:
        return None

    async def refresh(self, row: object) -> None:
        now = datetime.utcnow()
        for attr in ("created_at", "updated_at"):
            if hasattr(row, attr) and getattr(row, attr, None) is None:
                setattr(row, attr, now)


def _user() -> CurrentUser:
    return CurrentUser(
        id="user-1",
        email="user@example.com",
        display_name="User One",
    )


@pytest.mark.asyncio
async def test_create_org_auto_grants_owner_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.routes import orgs as orgs_routes

    session = _FakeAsyncSession()
    monkeypatch.setattr(orgs_routes, "_to_org", lambda row: {"id": row.id})
    await orgs_routes.create_org(
        body=orgs_routes.OrgIn(slug="acme", name="Acme"),
        session=session,  # type: ignore[arg-type]
        user=_user(),
    )

    grants = [row for row in session.added if isinstance(row, Membership)]
    assert len(grants) == 1
    grant = grants[0]
    assert grant.scope_kind == "org"
    assert grant.scope_id == "test-id-1"
    assert grant.role == "owner"
    assert grant.live_control is True
    assert grant.user_id == "user-1"
    assert grant.granted_by == "user-1"


@pytest.mark.asyncio
async def test_create_team_auto_grants_owner_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.routes import teams as teams_routes

    session = _FakeAsyncSession()
    monkeypatch.setattr(teams_routes, "_to_team", lambda row: {"id": row.id})
    await teams_routes.create_team(
        body=teams_routes.TeamIn(org_id="org-1", slug="quant", name="Quant Team"),
        session=session,  # type: ignore[arg-type]
        user=_user(),
    )

    grants = [row for row in session.added if isinstance(row, Membership)]
    assert len(grants) == 1
    grant = grants[0]
    assert grant.scope_kind == "team"
    assert grant.scope_id == "test-id-1"
    assert grant.role == "owner"
    assert grant.live_control is True
    assert grant.user_id == "user-1"
    assert grant.granted_by == "user-1"


@pytest.mark.asyncio
async def test_create_lab_owner_membership_has_live_control(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.routes import labs as labs_routes

    session = _FakeAsyncSession()
    monkeypatch.setattr(labs_routes, "_to_lab", lambda row: {"id": row.id})
    await labs_routes.create_lab(
        body=labs_routes.LabIn(workspace_id="ws-1", slug="research", name="Research Lab"),
        session=session,  # type: ignore[arg-type]
        user=_user(),
    )

    grants = [row for row in session.added if isinstance(row, Membership)]
    assert len(grants) == 1
    grant = grants[0]
    assert grant.scope_kind == "lab"
    assert grant.scope_id == "test-id-1"
    assert grant.role == "owner"
    assert grant.live_control is True
    assert grant.user_id == "user-1"
    assert grant.granted_by == "user-1"
