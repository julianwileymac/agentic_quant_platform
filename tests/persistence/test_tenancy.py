"""Tests for the tenancy ORM tables (Org > Team > User > Workspace > Project / Lab)."""
from __future__ import annotations

import pytest


def test_tenancy_models_register_in_metadata(in_memory_db) -> None:
    """All seven tenancy tables are part of Base.metadata."""
    from aqp.persistence.models import Base
    from aqp.persistence import models_tenancy  # noqa: F401 - force-register

    expected = {
        "organizations",
        "teams",
        "users",
        "workspaces",
        "projects",
        "labs",
        "memberships",
        "config_overlays",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_can_create_organization_with_minimum_fields(in_memory_db) -> None:
    from aqp.persistence import models_tenancy  # noqa: F401
    from aqp.persistence.models_tenancy import Organization

    Session = in_memory_db
    with Session() as session:
        org = Organization(slug="acme", name="Acme Inc")
        session.add(org)
        session.commit()
        session.refresh(org)
        assert org.id is not None
        assert org.slug == "acme"
        assert org.status == "active"


def test_workspace_inherits_org_via_fk(in_memory_db) -> None:
    from aqp.persistence import models_tenancy  # noqa: F401
    from aqp.persistence.models_tenancy import Organization, Workspace

    Session = in_memory_db
    with Session() as session:
        org = Organization(slug="acme", name="Acme Inc")
        session.add(org)
        session.flush()
        ws = Workspace(org_id=org.id, slug="alpha", name="Alpha Workspace")
        session.add(ws)
        session.commit()
        session.refresh(org)
        session.refresh(ws)
        assert ws.org_id == org.id


def test_workspace_unique_slug_per_org(in_memory_db) -> None:
    from aqp.persistence import models_tenancy  # noqa: F401
    from aqp.persistence.models_tenancy import Organization, Workspace

    Session = in_memory_db
    with Session() as session:
        org = Organization(slug="acme", name="Acme Inc")
        session.add(org)
        session.flush()
        session.add(Workspace(org_id=org.id, slug="alpha", name="A"))
        session.add(Workspace(org_id=org.id, slug="alpha", name="B"))
        with pytest.raises(Exception):
            session.commit()


def test_project_belongs_to_workspace(in_memory_db) -> None:
    from aqp.persistence import models_tenancy  # noqa: F401
    from aqp.persistence.models_tenancy import Organization, Project, Workspace

    Session = in_memory_db
    with Session() as session:
        org = Organization(slug="acme", name="Acme Inc")
        session.add(org)
        session.flush()
        ws = Workspace(org_id=org.id, slug="alpha", name="Alpha")
        session.add(ws)
        session.flush()
        proj = Project(workspace_id=ws.id, slug="trader-bot", name="Trader Bot")
        session.add(proj)
        session.commit()
        session.refresh(proj)
        assert proj.workspace_id == ws.id


def test_lab_belongs_to_workspace(in_memory_db) -> None:
    from aqp.persistence import models_tenancy  # noqa: F401
    from aqp.persistence.models_tenancy import Lab, Organization, Workspace

    Session = in_memory_db
    with Session() as session:
        org = Organization(slug="acme", name="Acme Inc")
        session.add(org)
        session.flush()
        ws = Workspace(org_id=org.id, slug="alpha", name="Alpha")
        session.add(ws)
        session.flush()
        lab = Lab(workspace_id=ws.id, slug="research", name="Research Notebook")
        session.add(lab)
        session.commit()
        session.refresh(lab)
        assert lab.workspace_id == ws.id


def test_membership_polymorphic_scope_kind(in_memory_db) -> None:
    from aqp.persistence import models_tenancy  # noqa: F401
    from aqp.persistence.models_tenancy import (
        Membership,
        Organization,
        User,
        Workspace,
    )

    Session = in_memory_db
    with Session() as session:
        org = Organization(slug="acme", name="Acme")
        session.add(org)
        session.flush()
        user = User(email="alice@example.com", display_name="Alice")
        session.add(user)
        session.flush()
        ws = Workspace(org_id=org.id, slug="alpha", name="Alpha")
        session.add(ws)
        session.flush()

        for scope_kind, scope_id in (
            ("org", org.id),
            ("workspace", ws.id),
        ):
            session.add(
                Membership(
                    user_id=user.id,
                    scope_kind=scope_kind,
                    scope_id=scope_id,
                    role="admin",
                )
            )
        session.commit()
        rows = session.query(Membership).filter(Membership.user_id == user.id).all()
        assert len(rows) == 2
        assert {r.scope_kind for r in rows} == {"org", "workspace"}


def test_config_overlay_unique_per_scope_namespace(in_memory_db) -> None:
    from aqp.persistence import models_tenancy  # noqa: F401
    from aqp.persistence.models_tenancy import ConfigOverlayRow

    Session = in_memory_db
    with Session() as session:
        session.add(
            ConfigOverlayRow(
                scope_kind="workspace",
                scope_id="ws-1",
                namespace="llm",
                payload={"provider": "openai"},
            )
        )
        session.add(
            ConfigOverlayRow(
                scope_kind="workspace",
                scope_id="ws-1",
                namespace="llm",
                payload={"provider": "anthropic"},
            )
        )
        with pytest.raises(Exception):
            session.commit()
