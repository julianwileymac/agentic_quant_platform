"""``/admin/ws`` — multiplexed admin WebSocket gateway.

A single WebSocket endpoint multiplexes named channels:

- ``telemetry`` — Prometheus stream-relay snapshots
- ``paper.<task_id>`` — Celery progress frames for a paper-trading run
- ``terraform.<run_id>`` — Terraform plan/apply log lines
- ``argo.<app>`` — ArgoCD sync status updates
- ``audit.tail`` — live ``AdminAuditEvent`` stream (RBAC-filtered)

Backed by Redis Streams (``aqp:admin:ws:<channel>``) so multiple
admin replicas can subscribe to the same upstream and emit
consistently. The client speaks a tiny JSON protocol:

::

    -> {"type": "subscribe", "channel": "paper.abc123"}
    <- {"type": "subscribed", "channel": "paper.abc123", "since": "$"}
    <- {"type": "frame", "channel": "paper.abc123", "data": {...}}
    -> {"type": "unsubscribe", "channel": "paper.abc123"}
    <- {"type": "unsubscribed", "channel": "paper.abc123"}
    -> {"type": "ping"}
    <- {"type": "pong", "timestamp": "..."}

Frames preserve the canonical Celery progress shape per AGENTS rule
4: ``{task_id, stage, message, timestamp, **extras}``. Channels are
namespaced by RBAC — the client cannot subscribe to ``audit.tail``
without ``read:infrastructure`` (or ``admin:cluster``).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, WebSocket, WebSocketDisconnect, status

from aqp_admin.deps.identity import _payload_to_admin, _ensure_validator
from aqp_admin.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Channel routing & RBAC
# ---------------------------------------------------------------------------

_CHANNEL_PATTERN = re.compile(
    r"^(?P<group>telemetry|paper|terraform|argo|audit)(?:\.(?P<key>[A-Za-z0-9_\-:]{1,80}))?$"
)

_CHANNEL_REQUIRED_SCOPES: dict[str, frozenset[str]] = {
    "telemetry": frozenset({"read:infrastructure"}),
    "paper": frozenset({"trade:read"}),
    "terraform": frozenset({"read:infrastructure"}),
    "argo": frozenset({"read:infrastructure"}),
    "audit": frozenset({"read:infrastructure"}),
}


def _redis_stream_key(channel: str) -> str:
    """Normalise a channel name into a Redis Stream key.

    Per ``.cursor/rules/cache.mdc`` the ``aqp:admin:ws:`` prefix is
    reserved for the admin WS bridge and never collides with the
    metadata-cache namespace (``aqp:cache:*``).
    """
    return f"aqp:admin:ws:{channel}"


def _channel_group(channel: str) -> str | None:
    match = _CHANNEL_PATTERN.match(channel)
    return match.group("group") if match else None


# ---------------------------------------------------------------------------
# Subscriber bookkeeping
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Subscription:
    channel: str
    last_id: str = "$"


@dataclass(slots=True)
class _Session:
    websocket: WebSocket
    user_sub: str
    user_scopes: frozenset[str]
    subscriptions: dict[str, _Subscription] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Redis bridge — soft optional dependency
# ---------------------------------------------------------------------------


_REDIS_CLIENT: Any = None


async def _get_redis() -> Any | None:
    """Return a lazy redis.asyncio client or ``None`` when unavailable.

    The admin BFF treats Redis as optional in the same way the audit
    sink treats the HTTP forwarder — degrade gracefully so local-dev
    contributors don't have to spin up a Redis instance just to load
    the dashboard.
    """
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    try:
        import redis.asyncio as redis_asyncio  # type: ignore[import-not-found]
    except ImportError:
        logger.info("redis.asyncio not installed; admin WS bridge runs in echo-only mode")
        return None
    redis_url = os.environ.get(
        "AQP_ADMIN_REDIS_URL",
        os.environ.get("AQP_REDIS_URL", "redis://localhost:6379/0"),
    )
    try:
        _REDIS_CLIENT = redis_asyncio.from_url(redis_url, decode_responses=True)
        await _REDIS_CLIENT.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin WS Redis unavailable (%s); echo-only mode", exc)
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


# ---------------------------------------------------------------------------
# Inbound auth (WebSocket cannot reuse the Depends dep chain ergonomically)
# ---------------------------------------------------------------------------


async def _authenticate_websocket(
    websocket: WebSocket,
    authorization: str | None,
) -> _Session | None:
    """Validate the JWT and resolve scopes; close the socket on failure.

    Local-dev (`auth_required=false`) accepts the connection with a
    synthesised anonymous user carrying ``admin:cluster`` so the SPA
    works on a fresh checkout.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        await websocket.accept()
        return _Session(
            websocket=websocket,
            user_sub="anonymous",
            user_scopes=frozenset({"admin:cluster"}),
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="missing bearer",
        )
        return None
    token = authorization.split(None, 1)[1].strip()

    validator = await _ensure_validator()
    if validator is None:
        await websocket.close(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="auth not configured",
        )
        return None

    try:
        payload = await validator.validate(token)
    except Exception:  # noqa: BLE001
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="invalid token",
        )
        return None

    user = _payload_to_admin(payload)
    await websocket.accept()
    return _Session(
        websocket=websocket,
        user_sub=user.sub,
        user_scopes=user.scopes,
    )


# ---------------------------------------------------------------------------
# Channel readers
# ---------------------------------------------------------------------------


async def _channel_reader(session: _Session, subscription: _Subscription) -> None:
    """Pump frames from Redis to the websocket until the channel ends."""
    redis = await _get_redis()
    if redis is None:
        # Echo-only mode — emit a single info frame so the operator
        # knows the bridge is degraded but the connection survives.
        await _send(
            session,
            {
                "type": "frame",
                "channel": subscription.channel,
                "data": {
                    "info": "redis_unavailable",
                    "message": (
                        "WS bridge running in echo-only mode (no Redis "
                        "connection); upstream events will not be relayed"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
        return

    stream_key = _redis_stream_key(subscription.channel)
    while subscription.channel in session.subscriptions:
        try:
            response = await redis.xread(
                {stream_key: subscription.last_id},
                count=64,
                block=2000,  # 2s block; cooperative shutdown on unsubscribe
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "WS Redis xread failed for %s: %s", subscription.channel, exc
            )
            await asyncio.sleep(2.0)
            continue
        if not response:
            continue
        # response shape: [[stream_key, [(id, {field: val}), ...]]]
        for _key, entries in response:
            for entry_id, fields in entries:
                subscription.last_id = entry_id
                payload_raw = fields.get("data") if isinstance(fields, dict) else None
                try:
                    data = json.loads(payload_raw) if payload_raw else dict(fields)
                except json.JSONDecodeError:
                    data = {"raw": payload_raw}
                await _send(
                    session,
                    {
                        "type": "frame",
                        "channel": subscription.channel,
                        "id": entry_id,
                        "data": data,
                    },
                )


# ---------------------------------------------------------------------------
# Outbound sender (serialise writes per session)
# ---------------------------------------------------------------------------


_SESSION_WRITE_LOCKS: dict[int, asyncio.Lock] = {}


async def _send(session: _Session, message: dict[str, Any]) -> None:
    lock = _SESSION_WRITE_LOCKS.setdefault(id(session), asyncio.Lock())
    async with lock:
        try:
            await session.websocket.send_text(json.dumps(message, default=str))
        except Exception as exc:  # noqa: BLE001
            logger.debug("WS send failed: %s", exc)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.websocket("/admin/ws")
async def admin_ws(
    websocket: WebSocket,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """Multiplexed admin WebSocket endpoint."""
    session = await _authenticate_websocket(websocket, authorization)
    if session is None:
        return

    reader_tasks: dict[str, asyncio.Task[None]] = {}
    try:
        await _send(
            session,
            {
                "type": "ready",
                "channels": sorted(_CHANNEL_REQUIRED_SCOPES.keys()),
                "user": session.user_sub,
            },
        )
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send(
                    session,
                    {"type": "error", "code": "invalid_json"},
                )
                continue
            mtype = str(message.get("type") or "").lower()
            channel = str(message.get("channel") or "")

            if mtype == "ping":
                await _send(
                    session,
                    {
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            if mtype == "subscribe":
                if not _channel_group(channel):
                    await _send(
                        session,
                        {
                            "type": "error",
                            "code": "invalid_channel",
                            "channel": channel,
                        },
                    )
                    continue
                group = _channel_group(channel) or ""
                required = _CHANNEL_REQUIRED_SCOPES.get(group, frozenset())
                if "admin:cluster" not in session.user_scopes and not (
                    required & session.user_scopes
                ):
                    await _send(
                        session,
                        {
                            "type": "error",
                            "code": "insufficient_scope",
                            "channel": channel,
                            "required": sorted(required),
                        },
                    )
                    continue
                if channel in session.subscriptions:
                    await _send(
                        session,
                        {"type": "subscribed", "channel": channel, "since": "(noop)"},
                    )
                    continue
                sub = _Subscription(channel=channel)
                session.subscriptions[channel] = sub
                reader_tasks[channel] = asyncio.create_task(
                    _channel_reader(session, sub)
                )
                await _send(
                    session,
                    {"type": "subscribed", "channel": channel, "since": sub.last_id},
                )
                continue

            if mtype == "unsubscribe":
                sub = session.subscriptions.pop(channel, None)
                task = reader_tasks.pop(channel, None)
                if task is not None:
                    task.cancel()
                await _send(
                    session,
                    {"type": "unsubscribed", "channel": channel},
                )
                continue

            await _send(session, {"type": "error", "code": "unknown_message_type"})

    finally:
        for task in reader_tasks.values():
            task.cancel()
        for task in reader_tasks.values():
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        _SESSION_WRITE_LOCKS.pop(id(session), None)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["router"]
