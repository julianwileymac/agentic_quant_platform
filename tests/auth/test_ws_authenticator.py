"""Phase 3a control-plane maturation tests — WebSocket authenticator.

Covers the four protocol outcomes:
- Happy path: valid first frame -> ``auth_ok`` ACK + populated context.
- Protocol error (4001): malformed first frame, missing token, or
  timeout waiting for the first frame.
- Token invalid (4003): JWT signature / audience / expiry failure.
- Insufficient scope (4008): per-endpoint scope check rejects.

The fake :class:`_FakeWebSocket` mimics the parts of
:class:`fastapi.WebSocket` that
:class:`aqp.auth.ws.WebSocketAuthenticator` actually touches, with
deterministic ordering so tests don't race.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

import pytest

from aqp.auth.scopes import AQPScope
from aqp.auth.ws import (
    WS_CLOSE_INSUFFICIENT_SCOPE,
    WS_CLOSE_PROTOCOL_ERROR,
    WS_CLOSE_TOKEN_INVALID,
    WebSocketAuthenticator,
    WebSocketAuthResult,
)


# ---------------------------------------------------------------------------
# FakeWebSocket — minimal stand-in for fastapi.WebSocket
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    """Deterministic in-memory WebSocket double for unit tests."""

    def __init__(self, *, incoming: list[str | None] | None = None) -> None:
        self._incoming: list[str | None] = list(incoming or [])
        self.sent: list[Any] = []
        self.closed: dict[str, Any] | None = None

    async def receive_text(self) -> str:
        if not self._incoming:
            # Simulate a slow client: never delivers anything.
            await asyncio.sleep(10)
        first = self._incoming.pop(0)
        if first is None:
            raise asyncio.TimeoutError()  # not actually used; see _Timeout
        return first

    async def send_json(self, payload: Any) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = {"code": code, "reason": reason}


class _ImmediateTimeoutWebSocket(_FakeWebSocket):
    """Force ``receive_text`` to time out immediately for protocol tests."""

    async def receive_text(self) -> str:
        # The authenticator wraps this in asyncio.wait_for(timeout=5.0);
        # raising TimeoutError here lets the wrapper see a timeout
        # without actually waiting 5 seconds.
        raise asyncio.TimeoutError()


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def authenticator() -> WebSocketAuthenticator:
    return WebSocketAuthenticator(timeout_seconds=0.01)


def _enable_strict_ws_auth():
    """Force ``settings.ws_auth_required`` to True for the duration of a test."""
    return patch("aqp.auth.ws._is_ws_auth_required", return_value=True)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Valid first frame -> auth_ok ACK + populated context."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_context(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        claims = {
            "sub": "user-1",
            "scope": "data:read data:write",
            "permissions": ["agent:execute"],
            "https://aqp.internal/workspace_id": "ws-42",
        }
        ws = _FakeWebSocket(
            incoming=[json.dumps({"type": "auth", "token": "good-token"})]
        )
        with patch("aqp.auth.ws.validate_jwt", return_value=claims):
            result = await authenticator.authenticate(ws)
        assert isinstance(result, WebSocketAuthResult)
        assert result.user_id == "user-1"
        assert result.context.workspace_id == "ws-42"
        assert AQPScope.READ_DATA in result.scopes
        assert AQPScope.WRITE_DATA in result.scopes
        assert AQPScope.AGENT_EXECUTE in result.scopes
        # ACK was sent
        assert ws.sent and ws.sent[0]["type"] == "auth_ok"
        assert ws.sent[0]["user_id"] == "user-1"
        # Socket was NOT closed
        assert ws.closed is None

    @pytest.mark.asyncio
    async def test_first_frame_overrides_workspace(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        claims = {"sub": "user-1"}
        ws = _FakeWebSocket(
            incoming=[
                json.dumps(
                    {
                        "type": "auth",
                        "token": "good-token",
                        "workspace_id": "ws-override",
                        "project_id": "proj-7",
                    }
                )
            ]
        )
        with patch("aqp.auth.ws.validate_jwt", return_value=claims):
            result = await authenticator.authenticate(ws)
        assert result is not None
        assert result.context.workspace_id == "ws-override"
        assert result.context.project_id == "proj-7"

    @pytest.mark.asyncio
    async def test_namespaced_roles_expand_via_canonical(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        # Both legacy ('admin') and canonical ('aqp-admin') role names
        # must produce the same scope set.
        legacy_claims = {
            "sub": "user-1",
            "https://aqp.internal/roles": ["admin"],
        }
        ws = _FakeWebSocket(
            incoming=[json.dumps({"type": "auth", "token": "tok"})]
        )
        with patch("aqp.auth.ws.validate_jwt", return_value=legacy_claims):
            result = await authenticator.authenticate(ws)
        assert result is not None
        assert AQPScope.WRITE_DATA in result.scopes
        assert AQPScope.MANAGE_INFRASTRUCTURE in result.scopes


# ---------------------------------------------------------------------------
# Protocol errors (close code 4001)
# ---------------------------------------------------------------------------


class TestProtocolErrors:
    """Invalid first frame -> close 4001 (in strict mode) or fallback."""

    @pytest.mark.asyncio
    async def test_missing_first_frame_strict_closes_4001(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        ws = _ImmediateTimeoutWebSocket()
        with _enable_strict_ws_auth():
            result = await authenticator.authenticate(ws)
        assert result is None
        assert ws.closed is not None
        assert ws.closed["code"] == WS_CLOSE_PROTOCOL_ERROR

    @pytest.mark.asyncio
    async def test_missing_first_frame_permissive_falls_back(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        # Default settings.ws_auth_required is False -> fallback context
        ws = _ImmediateTimeoutWebSocket()
        result = await authenticator.authenticate(ws)
        assert result is not None
        assert result.user_id  # default context has a user_id
        assert ws.closed is None

    @pytest.mark.asyncio
    async def test_non_json_first_frame_strict_closes(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        ws = _FakeWebSocket(incoming=["not json at all"])
        with _enable_strict_ws_auth():
            result = await authenticator.authenticate(ws)
        assert result is None
        assert ws.closed["code"] == WS_CLOSE_PROTOCOL_ERROR

    @pytest.mark.asyncio
    async def test_wrong_type_strict_closes(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        ws = _FakeWebSocket(
            incoming=[json.dumps({"type": "heartbeat"})]
        )
        with _enable_strict_ws_auth():
            result = await authenticator.authenticate(ws)
        assert result is None
        assert ws.closed["code"] == WS_CLOSE_PROTOCOL_ERROR

    @pytest.mark.asyncio
    async def test_missing_token_strict_closes(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        ws = _FakeWebSocket(incoming=[json.dumps({"type": "auth"})])
        with _enable_strict_ws_auth():
            result = await authenticator.authenticate(ws)
        assert result is None
        assert ws.closed["code"] == WS_CLOSE_PROTOCOL_ERROR


# ---------------------------------------------------------------------------
# Token invalid (close code 4003)
# ---------------------------------------------------------------------------


class TestTokenInvalid:
    """JWT signature / audience / expiry failure -> 4003."""

    @pytest.mark.asyncio
    async def test_invalid_token_closes_4003(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        from aqp.auth.oidc import InvalidTokenError

        ws = _FakeWebSocket(
            incoming=[json.dumps({"type": "auth", "token": "bad"})]
        )
        with patch(
            "aqp.auth.ws.validate_jwt",
            side_effect=InvalidTokenError("expired"),
        ):
            result = await authenticator.authenticate(ws)
        assert result is None
        assert ws.closed["code"] == WS_CLOSE_TOKEN_INVALID


# ---------------------------------------------------------------------------
# Insufficient scope (close code 4008)
# ---------------------------------------------------------------------------


class TestInsufficientScope:
    @pytest.mark.asyncio
    async def test_require_scope_closes_4008(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        claims = {"sub": "user-1", "scope": "data:read"}
        ws = _FakeWebSocket(
            incoming=[json.dumps({"type": "auth", "token": "good"})]
        )
        with patch("aqp.auth.ws.validate_jwt", return_value=claims):
            result = await authenticator.authenticate(ws)
        assert result is not None
        granted = await result.require_scope(ws, AQPScope.TRADE_LIVE)
        assert granted is False
        assert ws.closed["code"] == WS_CLOSE_INSUFFICIENT_SCOPE

    @pytest.mark.asyncio
    async def test_platform_admin_satisfies_any_scope(
        self, authenticator: WebSocketAuthenticator
    ) -> None:
        claims = {
            "sub": "user-1",
            "https://aqp.internal/scopes": [AQPScope.PLATFORM_ADMIN],
        }
        ws = _FakeWebSocket(
            incoming=[json.dumps({"type": "auth", "token": "good"})]
        )
        with patch("aqp.auth.ws.validate_jwt", return_value=claims):
            result = await authenticator.authenticate(ws)
        assert result is not None
        granted = await result.require_scope(ws, AQPScope.TRADE_LIVE)
        assert granted is True
        # No close happened
        assert ws.closed is None


__all__: list[str] = []
