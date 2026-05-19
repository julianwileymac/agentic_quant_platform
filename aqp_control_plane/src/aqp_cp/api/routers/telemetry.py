"""``/manage/telemetry`` — point-in-time snapshot + WebSocket stream."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from aqp_cp.auth.deps import AuthenticatedUser, require_auth, require_scope
from aqp_cp.auth.validator import validate_bearer_token
from aqp_cp.models import (
    AlertEvent,
    HealthStatus,
    MetricPoint,
    ProviderHealth,
    ResponseEnvelope,
)
from aqp_cp.services.lifecycle import get_active_provider
from aqp_cp.services.telemetry import get_supervisor
from aqp_cp.settings import get_settings

router = APIRouter(tags=["telemetry"])


@router.get(
    "/telemetry/snapshot",
    summary="Point-in-time provider health snapshot.",
    response_model=ResponseEnvelope[ProviderHealth],
)
async def telemetry_snapshot(
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[ProviderHealth]:
    provider = get_active_provider()
    health = await provider.health()
    return ResponseEnvelope(status="ok", data=health)


@router.websocket("/telemetry/stream/{service_id}")
async def telemetry_stream(
    websocket: WebSocket,
    service_id: str,
    namespace: str | None = None,
    token: str | None = None,
) -> None:
    """Stream :class:`MetricPoint` + :class:`AlertEvent` frames for ``service_id``.

    Auth: the inbound WebSocket carries a Bearer token either in the
    ``Authorization`` header (preferred) or as a ``?token=...`` query
    parameter (browser fallback — `WebSocket` API can't set headers).
    """
    settings = get_settings()

    if settings.auth_enabled:
        # Resolve token from header OR query string.
        auth_header = websocket.headers.get("authorization")
        bearer: str | None = None
        if auth_header and auth_header.lower().startswith("bearer "):
            bearer = auth_header.split(None, 1)[1].strip()
        elif token:
            bearer = token.strip()
        if not bearer:
            await websocket.close(code=4401, reason="missing_bearer_token")
            return
        try:
            payload = await validate_bearer_token(bearer)
        except Exception as exc:  # noqa: BLE001
            await websocket.close(code=4401, reason=str(exc)[:120])
            return
        # Minimal scope check on the validated payload.
        scopes = set((payload.get("scope") or "").split())
        scopes.update(str(p) for p in (payload.get("permissions") or []))
        if "read:infrastructure" not in scopes and "admin:cluster" not in scopes:
            await websocket.close(code=4403, reason="insufficient_scope")
            return

    await websocket.accept()
    supervisor = await get_supervisor()
    subscriber = await supervisor.subscribe(service_id, namespace=namespace)

    try:
        while True:
            try:
                item = await asyncio.wait_for(subscriber.queue.get(), timeout=30)
            except asyncio.TimeoutError:
                # Heartbeat — keep idle connections alive through proxies.
                await websocket.send_json(
                    {
                        "task_id": service_id,
                        "stage": "heartbeat",
                        "message": "telemetry idle",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                continue
            await websocket.send_json(_serialise(item, service_id))
    except WebSocketDisconnect:
        return
    finally:
        await supervisor.unsubscribe(service_id, subscriber)


def _serialise(item: MetricPoint | AlertEvent, service_id: str) -> dict:
    """Adapt provider frames to the canonical AQP progress shape (rule 4)."""
    if isinstance(item, AlertEvent):
        return {
            "task_id": service_id,
            "stage": "alert",
            "message": item.message,
            "timestamp": item.timestamp.isoformat(),
            "alert": item.model_dump(mode="json"),
        }
    return {
        "task_id": service_id,
        "stage": "metric",
        "message": f"{item.metric}={item.value}",
        "timestamp": item.timestamp.isoformat(),
        "metric": item.model_dump(mode="json"),
    }


__all__ = ["router"]
