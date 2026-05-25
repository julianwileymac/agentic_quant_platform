"""AdminAuditSink — JSONL writes + redaction + event lifecycle."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aqp_admin.audit.sink import (
    AdminAuditEvent,
    JsonlAdminAuditSink,
    LoggingAdminAuditSink,
    build_default_audit_sink,
    finalise_event,
    new_event,
    reset_audit_sink,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_audit_sink()
    monkeypatch.delenv("AQP_ADMIN_AUDIT_SINK", raising=False)
    monkeypatch.delenv("AQP_ADMIN_AUDIT_JSONL_PATH", raising=False)
    from aqp_admin.settings import reset_settings_cache

    reset_settings_cache()


def test_new_event_redacts_secret_payload() -> None:
    event = new_event(
        action="admin.test",
        target="x",
        actor_sub="auth0|abc",
        payload={"client_secret": "hunter2", "okay": "value"},
    )
    assert event.payload["client_secret"] == "<redacted>"
    assert event.payload["okay"] == "value"


def test_finalise_event_stamps_duration() -> None:
    event = new_event(action="admin.test", target="x", actor_sub="auth0|abc")
    out = finalise_event(event, status="succeeded", result={"ok": True})
    assert out.status == "succeeded"
    assert out.result == {"ok": True}
    assert out.duration_ms is not None and out.duration_ms >= 0.0


def test_jsonl_sink_appends_phase_rows(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    sink = JsonlAdminAuditSink(str(log))
    event = new_event(action="admin.create_org", target="acme", actor_sub="auth0|abc")
    sink.start(event)
    sink.finish(finalise_event(event, status="succeeded"))
    lines = log.read_text().strip().splitlines()
    rows = [json.loads(line) for line in lines]
    assert rows[0]["phase"] == "start"
    assert rows[1]["phase"] == "finish"
    assert rows[0]["action"] == "admin.create_org"
    assert rows[1]["status"] == "succeeded"


def test_default_sink_falls_back_to_logger_when_http_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AQP_ADMIN_AUDIT_SINK", "http")
    monkeypatch.delenv("AQP_ADMIN_AUDIT_HTTP_URL", raising=False)
    from aqp_admin.settings import reset_settings_cache

    reset_settings_cache()
    sink = build_default_audit_sink()
    assert isinstance(sink, LoggingAdminAuditSink)
