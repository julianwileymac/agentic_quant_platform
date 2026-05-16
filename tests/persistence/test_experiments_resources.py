"""Smoke tests for the Phase 1 ORM (experiments / tests / resources).

These tests intentionally only exercise import + simple in-memory
SQLite round-trips so they run fast without a Postgres dependency.
The full FK / cross-table joins are exercised by Phase 2 graph tests.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session


@pytest.fixture
def sqlite_session() -> Session:
    """In-memory SQLite session with the experiment / resource subgraph created.

    We only create the tables that don't have outgoing FKs into the
    larger tenancy / run graph; this lets the ORM smoke-test run without
    pulling in every model.

    SQLite ships with FK enforcement OFF by default; turn it on so
    ``ondelete=CASCADE`` actually fires and the umbrella delete cascades
    to ``tests``. Real deployments use Postgres which always enforces FKs.
    """
    from aqp.persistence.models import Base
    from aqp.persistence import (
        models_experiments,  # noqa: F401 - registers tables on Base
        models_resources,    # noqa: F401 - registers tables on Base
        models_tenancy,      # noqa: F401 - the FK parents
    )

    from aqp.config.defaults import (
        DEFAULT_LAB_ID,
        DEFAULT_ORG_ID,
        DEFAULT_PROJECT_ID,
        DEFAULT_TEAM_ID,
        DEFAULT_USER_ID,
        DEFAULT_WORKSPACE_ID,
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
        Base.metadata.tables["aqp_experiments"],
        Base.metadata.tables["aqp_tests"],
        Base.metadata.tables["aqp_resources"],
        Base.metadata.tables["aqp_resource_relations"],
    ]
    Base.metadata.create_all(engine, tables=tables)

    # Seed the default tenancy rows so the ProjectScopedMixin's
    # ``default=DEFAULT_*_ID`` values point at rows that actually exist.
    # In production these are populated by migration 0017_tenancy_foundation.
    from aqp.persistence.models_tenancy import (
        Lab,
        Organization,
        Project,
        Team,
        User,
        Workspace,
    )

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
    return sess


def test_experiment_default_kind_and_status(sqlite_session: Session) -> None:
    from aqp.persistence.models_experiments import Experiment

    row = Experiment(
        slug="hyp-1",
        name="Hypothesis 1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    sqlite_session.add(row)
    sqlite_session.flush()
    sqlite_session.refresh(row)
    assert row.kind == "research"
    assert row.status == "draft"


def test_experiment_parent_self_reference(sqlite_session: Session) -> None:
    from aqp.persistence.models_experiments import Experiment

    parent = Experiment(
        slug="sweep",
        name="Sweep",
        kind="sweep",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    sqlite_session.add(parent)
    sqlite_session.flush()

    child = Experiment(
        slug="abl-1",
        name="Ablation 1",
        kind="ablation",
        parent_experiment_id=parent.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    sqlite_session.add(child)
    sqlite_session.flush()
    sqlite_session.refresh(child)
    assert child.parent_experiment_id == parent.id


def test_test_cascade_on_experiment_delete(sqlite_session: Session) -> None:
    from aqp.persistence.models_experiments import Experiment, Test

    exp = Experiment(
        slug="e1",
        name="E1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    sqlite_session.add(exp)
    sqlite_session.flush()

    test_row = Test(
        experiment_id=exp.id,
        slug="sharpe-gt-1",
        name="Sharpe > 1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    sqlite_session.add(test_row)
    sqlite_session.flush()
    test_id = test_row.id

    sqlite_session.delete(exp)
    sqlite_session.commit()
    # Drop the identity map so .get() re-reads from the DB rather than
    # returning the stale Python object the test originally added.
    sqlite_session.expire_all()

    from aqp.persistence.models_experiments import Test as TestModel

    assert sqlite_session.get(TestModel, test_id) is None


def test_resource_polymorphic_owner(sqlite_session: Session) -> None:
    from aqp.persistence.models_resources import Resource

    row = Resource(
        name="MACD trend (lean)",
        slug="macd-trend",
        resource_type="strategy_template",
        owner_scope_kind="organization",
        owner_scope_id="00000000-0000-0000-0000-000000000001",
        uri="lean://algorithm.python/MACDTrendAlgorithm",
        meta={"tags": ["momentum", "indicators"]},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    sqlite_session.add(row)
    sqlite_session.flush()
    sqlite_session.refresh(row)
    assert row.owner_scope_kind == "organization"
    assert row.visibility == "private"  # server_default


def test_resource_relation_unique_edge(sqlite_session: Session) -> None:
    from aqp.persistence.models_resources import Resource, ResourceRelation

    a = Resource(
        name="A",
        slug="a",
        resource_type="config",
        owner_scope_kind="user",
        owner_scope_id="u1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    b = Resource(
        name="B",
        slug="b",
        resource_type="config",
        owner_scope_kind="user",
        owner_scope_id="u1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    sqlite_session.add_all([a, b])
    sqlite_session.flush()

    sqlite_session.add(
        ResourceRelation(
            from_id=a.id, to_id=b.id, relation="derived_from", created_at=datetime.utcnow()
        )
    )
    sqlite_session.flush()

    # Same edge twice violates the unique constraint.
    sqlite_session.add(
        ResourceRelation(
            from_id=a.id, to_id=b.id, relation="derived_from", created_at=datetime.utcnow()
        )
    )
    with pytest.raises(Exception):
        sqlite_session.flush()
