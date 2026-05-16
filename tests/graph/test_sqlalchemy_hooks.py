"""Verify SQLAlchemy after_flush_postexec emits ownership events.

Uses an in-memory SQLite session pre-seeded with the default tenancy
rows (mirrors the fixture used in tests/persistence/test_experiments_resources.py).
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from aqp.graph.events import (
    OwnershipEventKind,
    iter_drained_events,
    reset_fallback_queue_for_tests,
)
from aqp.graph.sqlalchemy_hooks import (
    register_hooks,
    unregister_hooks_for_tests,
)


@pytest.fixture
def sqlite_session(monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.setattr("aqp.graph.events._redis_client", lambda: None)
    reset_fallback_queue_for_tests()
    register_hooks()

    from aqp.config.defaults import (
        DEFAULT_LAB_ID,
        DEFAULT_ORG_ID,
        DEFAULT_PROJECT_ID,
        DEFAULT_TEAM_ID,
        DEFAULT_USER_ID,
        DEFAULT_WORKSPACE_ID,
    )
    from aqp.persistence import (
        models_experiments,  # noqa: F401
        models_resources,    # noqa: F401
        models_tenancy,      # noqa: F401
    )
    from aqp.persistence.models import Base
    from aqp.persistence.models_tenancy import (
        Lab,
        Organization,
        Project,
        Team,
        User,
        Workspace,
    )

    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _conn_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [
        Base.metadata.tables["organizations"],
        Base.metadata.tables["teams"],
        Base.metadata.tables["users"],
        Base.metadata.tables["workspaces"],
        Base.metadata.tables["projects"],
        Base.metadata.tables["labs"],
        Base.metadata.tables["memberships"],
        Base.metadata.tables["aqp_experiments"],
        Base.metadata.tables["aqp_tests"],
        Base.metadata.tables["aqp_resources"],
        Base.metadata.tables["aqp_resource_relations"],
    ]
    Base.metadata.create_all(engine, tables=tables)
    sess = Session(engine)

    sess.add(Organization(id=DEFAULT_ORG_ID, slug="default", name="Default Org"))
    sess.flush()
    sess.add(Team(id=DEFAULT_TEAM_ID, org_id=DEFAULT_ORG_ID, slug="default", name="Default Team"))
    sess.add(
        User(
            id=DEFAULT_USER_ID,
            email="default@example.com",
            display_name="Default",
            auth_subject="default",
            auth_provider="local",
        )
    )
    sess.add(Workspace(id=DEFAULT_WORKSPACE_ID, org_id=DEFAULT_ORG_ID, slug="default", name="Default Workspace"))
    sess.flush()
    sess.add(
        Project(
            id=DEFAULT_PROJECT_ID,
            workspace_id=DEFAULT_WORKSPACE_ID,
            slug="default",
            name="Default Project",
        )
    )
    sess.add(
        Lab(
            id=DEFAULT_LAB_ID,
            workspace_id=DEFAULT_WORKSPACE_ID,
            slug="default",
            name="Default Lab",
        )
    )
    sess.commit()
    # Drain everything the seed rows emitted so each test starts clean.
    list(iter_drained_events(max_events=10000))
    yield sess
    unregister_hooks_for_tests()
    reset_fallback_queue_for_tests()


def test_create_experiment_emits_node_and_edges(sqlite_session: Session) -> None:
    from aqp.persistence.models_experiments import Experiment

    row = Experiment(
        slug="hyp",
        name="Hypothesis",
        kind="research",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    sqlite_session.add(row)
    sqlite_session.commit()

    events = list(iter_drained_events(max_events=100))
    nodes = [e for e in events if e.kind == OwnershipEventKind.UPSERT_NODE]
    edges = [e for e in events if e.kind == OwnershipEventKind.UPSERT_EDGE]
    assert any(
        e.node and e.node.kind == "Experiment" and e.node.id == row.id for e in nodes
    )
    assert any(
        e.edge
        and e.edge.from_kind == "Experiment"
        and e.edge.to_kind == "Project"
        and e.edge.relation == "IN_PROJECT"
        for e in edges
    )


def test_create_resource_emits_owns_edge(sqlite_session: Session) -> None:
    from aqp.persistence.models_resources import Resource

    row = Resource(
        name="Template",
        slug="tpl",
        resource_type="strategy_template",
        owner_scope_kind="user",
        owner_scope_id="00000000-0000-0000-0000-000000000003",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    sqlite_session.add(row)
    sqlite_session.commit()

    events = list(iter_drained_events(max_events=100))
    owns = [
        e
        for e in events
        if e.edge and e.edge.relation == "OWNS"
    ]
    assert owns, "OWNS edge missing for new Resource"
    assert owns[0].edge.from_kind == "User"


def test_membership_creates_member_of_edge(sqlite_session: Session) -> None:
    from aqp.persistence.models_tenancy import Membership

    sqlite_session.add(
        Membership(
            user_id="00000000-0000-0000-0000-000000000003",
            scope_kind="workspace",
            scope_id="00000000-0000-0000-0000-000000000004",
            role="owner",
            live_control=True,
            granted_by="00000000-0000-0000-0000-000000000003",
        )
    )
    sqlite_session.commit()

    events = list(iter_drained_events(max_events=100))
    member_of = [
        e
        for e in events
        if e.edge and e.edge.relation == "MEMBER_OF" and e.edge.to_kind == "Workspace"
    ]
    assert member_of
    assert member_of[0].edge.properties.get("role") == "owner"
