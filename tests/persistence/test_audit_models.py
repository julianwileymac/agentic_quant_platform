"""Persistence tests for security audit events."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession


def _prepare_schema(session: OrmSession) -> None:
    from aqp.persistence import models_audit, models_tenancy  # noqa: F401
    from aqp.persistence.models import Base

    session.execute(sa.text("PRAGMA foreign_keys = ON"))
    Base.metadata.create_all(bind=session.get_bind())


def test_security_audit_event_round_trip_insert_and_query(in_memory_db) -> None:
    from aqp.persistence.models_audit import SecurityAuditEvent
    from aqp.persistence.models_tenancy import Organization, User, Workspace

    Session = in_memory_db
    with Session() as session:
        _prepare_schema(session)
        org = Organization(slug="audit-org", name="Audit Org")
        session.add(org)
        session.flush()
        workspace = Workspace(org_id=org.id, slug="audit-ws", name="Audit Workspace")
        session.add(workspace)
        user = User(email="audit.user@example.com", display_name="Audit User")
        session.add(user)
        session.flush()

        event = SecurityAuditEvent(
            user_id=user.id,
            organization_id=org.id,
            workspace_id=workspace.id,
            event_type="login",
            event_category="authn",
            severity="info",
            source="api",
            details={"result": "success"},
        )
        session.add(event)
        session.commit()

        row = (
            session.query(SecurityAuditEvent)
            .filter(SecurityAuditEvent.id == event.id)
            .one()
        )
        assert row.event_type == "login"
        assert row.details == {"result": "success"}
        assert row.created_at is not None


def test_security_audit_event_cascades_on_workspace_delete(in_memory_db) -> None:
    from aqp.persistence.models_audit import SecurityAuditEvent
    from aqp.persistence.models_tenancy import Organization, Workspace

    Session = in_memory_db
    with Session() as session:
        _prepare_schema(session)
        org = Organization(slug="cascade-org", name="Cascade Org")
        session.add(org)
        session.flush()
        workspace = Workspace(org_id=org.id, slug="cascade-ws", name="Cascade Workspace")
        session.add(workspace)
        session.flush()
        event = SecurityAuditEvent(
            organization_id=org.id,
            workspace_id=workspace.id,
            event_type="kill_switch",
            event_category="safety",
            severity="critical",
            source="api",
            details={"enabled": True},
        )
        session.add(event)
        session.commit()
        event_id = event.id

        session.delete(workspace)
        session.commit()
        assert session.query(SecurityAuditEvent).filter_by(id=event_id).count() == 0


def test_security_audit_event_cascades_on_user_delete(in_memory_db) -> None:
    from aqp.persistence.models_audit import SecurityAuditEvent
    from aqp.persistence.models_tenancy import User

    Session = in_memory_db
    with Session() as session:
        _prepare_schema(session)
        user = User(email="delete.user@example.com", display_name="Delete User")
        session.add(user)
        session.flush()
        event = SecurityAuditEvent(
            user_id=user.id,
            actor_user_id=user.id,
            event_type="auth_failure",
            event_category="authn",
            severity="warning",
            source="api",
            details={"reason": "bad_password"},
        )
        session.add(event)
        session.commit()
        event_id = event.id

        session.delete(user)
        session.commit()
        assert session.query(SecurityAuditEvent).filter_by(id=event_id).count() == 0


def test_security_audit_event_required_columns_have_expected_nullability() -> None:
    from aqp.persistence.models_audit import SecurityAuditEvent

    columns = SecurityAuditEvent.__table__.c
    required = {
        "id",
        "event_type",
        "event_category",
        "severity",
        "source",
        "details",
        "created_at",
    }
    optional = {
        "user_id",
        "organization_id",
        "workspace_id",
        "ip",
        "user_agent",
        "actor_user_id",
        "connection",
        "request_id",
    }
    for name in required:
        assert columns[name].nullable is False, f"{name} should be NOT NULL"
    for name in optional:
        assert columns[name].nullable is True, f"{name} should be nullable"
