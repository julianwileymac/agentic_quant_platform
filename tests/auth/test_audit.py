"""Tests for :mod:`aqp.auth.audit`."""
from __future__ import annotations

import logging
import sys
import types
import uuid
from typing import Any

import pytest

from aqp.auth.audit import emit_audit_event


def _ensure_audit_model(monkeypatch: pytest.MonkeyPatch) -> type[Any]:
    try:
        from aqp.persistence.models_audit import SecurityAuditEvent

        return SecurityAuditEvent
    except Exception:
        from sqlalchemy import JSON, Column, DateTime, String, func

        from aqp.persistence.models import Base

        fallback = sys.modules.get("aqp.persistence.models_audit")
        if fallback is not None and hasattr(fallback, "SecurityAuditEvent"):
            return getattr(fallback, "SecurityAuditEvent")

        class SecurityAuditEvent(Base):
            __tablename__ = "security_audit_events"
            __table_args__ = {"extend_existing": True}

            id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
            user_id = Column(String, nullable=True)
            organization_id = Column(String, nullable=True)
            workspace_id = Column(String, nullable=True)
            event_type = Column(String, nullable=False)
            event_category = Column(String, nullable=False)
            severity = Column(String, nullable=False)
            source = Column(String, nullable=False)
            ip = Column(String, nullable=True)
            user_agent = Column(String, nullable=True)
            actor_user_id = Column(String, nullable=True)
            connection = Column(String, nullable=True)
            request_id = Column(String, nullable=True)
            details = Column(JSON, nullable=False, default=dict)
            created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

        module = types.ModuleType("aqp.persistence.models_audit")
        module.SecurityAuditEvent = SecurityAuditEvent
        monkeypatch.setitem(sys.modules, "aqp.persistence.models_audit", module)
        return SecurityAuditEvent


def _make_request(headers: dict[str, str], client_host: str = "127.0.0.1"):
    from starlette.requests import Request

    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in headers.items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/audit-test",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_host, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


@pytest.fixture
def audit_model(in_memory_db, monkeypatch: pytest.MonkeyPatch):
    model = _ensure_audit_model(monkeypatch)
    Session = in_memory_db
    with Session() as session:
        model.__table__.create(bind=session.bind, checkfirst=True)
    return model


@pytest.fixture
def audit_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_invite_secret", "test-invite-secret", raising=False)
    monkeypatch.setattr(settings, "auth_audit_enabled", True, raising=False)


def test_emit_audit_event_writes_row(in_memory_db, audit_model, audit_settings) -> None:
    emit_audit_event(
        "login",
        user_id="user-1",
        organization_id="org-1",
        workspace_id="ws-1",
        event_category="authn",
        source="api",
        details={"provider": "auth0"},
    )

    Session = in_memory_db
    with Session() as session:
        rows = session.query(audit_model).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.event_type == "login"
        assert row.user_id == "user-1"
        assert row.organization_id == "org-1"
        assert row.workspace_id == "ws-1"
        assert row.actor_user_id == "user-1"
        assert row.details == {"provider": "auth0"}


def test_emit_audit_event_noop_when_disabled(
    in_memory_db,
    audit_model,
    audit_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_audit_enabled", False, raising=False)

    emit_audit_event("login", user_id="user-disabled", details={"k": "v"})

    Session = in_memory_db
    with Session() as session:
        rows = session.query(audit_model).all()
        assert rows == []


def test_emit_audit_event_never_raises_on_db_error(
    audit_model,
    audit_settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from aqp.persistence import db as db_mod

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(db_mod, "get_session", _boom)
    with caplog.at_level(logging.WARNING):
        result = emit_audit_event("login", user_id="user-db-fail")
    assert result is None
    assert any("audit.emit_failed" in record.getMessage() for record in caplog.records)


def test_emit_audit_event_resolves_ip_from_xff(
    in_memory_db,
    audit_model,
    audit_settings,
) -> None:
    request = _make_request(
        {
            "X-Forwarded-For": "1.2.3.4, 5.6.7.8",
            "X-Real-IP": "9.9.9.9",
            "User-Agent": "pytest-agent",
        },
        client_host="8.8.8.8",
    )

    emit_audit_event(
        "login",
        user_id="user-ip",
        request=request,
        details={"where": "xff"},
    )

    Session = in_memory_db
    with Session() as session:
        row = session.query(audit_model).one()
        assert row.ip == "1.2.3.4"


def test_emit_audit_event_resolves_trace_id_when_available(
    in_memory_db,
    audit_model,
    audit_settings,
) -> None:
    otel_trace = pytest.importorskip("opentelemetry.trace")
    trace_id_hex = "0123456789abcdef0123456789abcdef"
    span_context = otel_trace.SpanContext(
        trace_id=int(trace_id_hex, 16),
        span_id=int("0123456789abcdef", 16),
        is_remote=False,
        trace_flags=otel_trace.TraceFlags(0x01),
        trace_state=otel_trace.TraceState(),
    )
    span = otel_trace.NonRecordingSpan(span_context)

    with otel_trace.use_span(span, end_on_exit=False):
        emit_audit_event("login", user_id="user-trace", details={"trace": True})

    Session = in_memory_db
    with Session() as session:
        row = session.query(audit_model).one()
        assert row.request_id == trace_id_hex
