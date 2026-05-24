"""Tests for :mod:`aqp.api.routes.auth0_log_stream` (AGENTS hard rule 53)."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aqp.api.routes.auth0_log_stream import (
    _classify,
    _coerce_event,
    _parse_payload,
    _verify_authorization,
    router,
)


# ---------------------------------------------------------------------------
# Pure-helper tests
# ---------------------------------------------------------------------------


def test_classify_revocation_events_critical() -> None:
    cat, sev = _classify("sdu")
    assert cat == "safety"
    assert sev == "critical"


def test_classify_failure_events_warning() -> None:
    cat, sev = _classify("fp")  # failed password
    assert cat == "authn"
    assert sev == "warning"


def test_classify_unknown_event_defaults_to_info() -> None:
    cat, sev = _classify("unknown_event")
    assert cat == "authn"
    assert sev == "info"


def test_parse_payload_handles_json_array() -> None:
    body = b'[{"type": "s", "user_id": "auth0|abc"}, {"type": "f"}]'
    parsed = _parse_payload(body)
    assert len(parsed) == 2
    assert parsed[0]["type"] == "s"


def test_parse_payload_handles_jsonlines() -> None:
    body = (
        b'{"type": "s", "user_id": "auth0|abc"}\n'
        b'{"type": "f", "user_id": "auth0|def"}\n'
    )
    parsed = _parse_payload(body)
    assert len(parsed) == 2
    assert parsed[1]["user_id"] == "auth0|def"


def test_parse_payload_skips_invalid_lines() -> None:
    body = b'{"type": "s"}\n{not-json}\n{"type": "f"}\n'
    parsed = _parse_payload(body)
    assert len(parsed) == 2


def test_parse_payload_empty_returns_empty_list() -> None:
    assert _parse_payload(b"") == []
    assert _parse_payload(b"   \n   ") == []


def test_coerce_event_unwraps_data_field() -> None:
    raw = {"data": {"type": "s", "user_id": "auth0|x"}, "log_id": "log-1"}
    coerced = _coerce_event(raw)
    assert coerced["type"] == "s"
    assert coerced["log_id"] == "log-1"


def test_coerce_event_handles_flat_payload() -> None:
    raw = {"type": "f", "user_id": "auth0|y"}
    coerced = _coerce_event(raw)
    assert coerced["type"] == "f"


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def test_verify_authorization_rejects_when_no_secret_configured() -> None:
    class _Stub:
        auth0_log_stream_secret = ""

    with patch("aqp.api.routes.auth0_log_stream.settings", _Stub()):
        assert _verify_authorization("Bearer xyz") is False


def test_verify_authorization_accepts_correct_secret_with_bearer_prefix() -> None:
    class _Stub:
        auth0_log_stream_secret = "my-secret"

    with patch("aqp.api.routes.auth0_log_stream.settings", _Stub()):
        assert _verify_authorization("Bearer my-secret") is True
        assert _verify_authorization("my-secret") is True
        assert _verify_authorization("Bearer wrong-secret") is False
        assert _verify_authorization(None) is False


# ---------------------------------------------------------------------------
# End-to-end route test
# ---------------------------------------------------------------------------


@pytest.fixture
def webhook_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_log_stream_route_401_without_secret(webhook_client: TestClient) -> None:
    response = webhook_client.post("/_internal/auth0/log-stream", content=b'{"type": "s"}')
    assert response.status_code == 401


def test_log_stream_route_accepts_authorised_payload(webhook_client: TestClient) -> None:
    class _Stub:
        auth0_log_stream_secret = "my-secret"
        auth0_log_stream_max_age_seconds = 86400

    enqueued: list[dict[str, Any]] = []

    class _FakeTask:
        def delay(self, **kwargs: Any) -> None:
            enqueued.append(kwargs)

    fake_module = type(
        "FakeMod",
        (),
        {"cleanup_for_user": _FakeTask()},
    )

    with patch("aqp.api.routes.auth0_log_stream.settings", _Stub()), patch(
        "aqp.tasks.session_revocation_tasks", fake_module
    ), patch("aqp.api.routes.auth0_log_stream._resolve_internal_user_id", return_value="internal-123"), patch(
        "aqp.auth.audit.emit_audit_event"
    ):
        body = b'{"type": "sdu", "user_id": "auth0|abc"}\n{"type": "s", "user_id": "auth0|abc"}'
        response = webhook_client.post(
            "/_internal/auth0/log-stream",
            content=body,
            headers={"Authorization": "Bearer my-secret"},
        )
    assert response.status_code == 202
    payload = response.json()
    assert payload["accepted"] == 2
    assert payload["processed"] == 2
    # Only the sdu (session-revoke) event triggers cleanup.
    assert payload["revoked_for_cleanup"] == 1
    assert len(enqueued) == 1
    assert enqueued[0]["reason"] == "sdu"
