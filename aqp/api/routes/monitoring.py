"""Global run monitoring endpoints backed by Celery inspect/control."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from aqp.tasks.celery_app import celery_app

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


RunPosition = Literal["active", "reserved", "scheduled"]


class MonitoringRun(BaseModel):
    task_id: str
    name: str
    state: str
    position: RunPosition
    worker: str
    queue: str | None = None
    args: str | None = None
    kwargs: str | None = None
    eta: str | None = None
    time_start: float | None = None
    retries: int | None = None


class MonitoringRunsResponse(BaseModel):
    generated_at: datetime
    workers_seen: int
    active: list[MonitoringRun] = Field(default_factory=list)
    reserved: list[MonitoringRun] = Field(default_factory=list)
    scheduled: list[MonitoringRun] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class RevokeRunRequest(BaseModel):
    terminate: bool = False
    signal: str = "SIGTERM"


def _inspect_payload(method: str) -> tuple[dict[str, list[dict[str, Any]]], str | None]:
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        payload = getattr(inspector, method)() or {}
    except Exception as exc:  # noqa: BLE001
        return {}, str(exc)
    if not isinstance(payload, dict):
        return {}, f"unexpected inspect payload for {method}"
    return payload, None


def _request_for(position: RunPosition, raw: dict[str, Any]) -> dict[str, Any]:
    if position == "scheduled" and isinstance(raw.get("request"), dict):
        return raw["request"]
    return raw


def _queue_for(request: dict[str, Any]) -> str | None:
    delivery = request.get("delivery_info")
    if not isinstance(delivery, dict):
        return None
    for key in ("routing_key", "queue", "exchange"):
        value = delivery.get(key)
        if value:
            return str(value)
    return None


def _normalise_run(position: RunPosition, worker: str, raw: dict[str, Any]) -> MonitoringRun | None:
    request = _request_for(position, raw)
    task_id = request.get("id")
    if not task_id:
        return None
    state = celery_app.AsyncResult(str(task_id)).state
    return MonitoringRun(
        task_id=str(task_id),
        name=str(request.get("name") or request.get("type") or "unknown"),
        state=str(state),
        position=position,
        worker=worker,
        queue=_queue_for(request),
        args=str(request.get("args")) if request.get("args") is not None else None,
        kwargs=str(request.get("kwargs")) if request.get("kwargs") is not None else None,
        eta=str(raw.get("eta") or request.get("eta") or "") or None,
        time_start=float(request["time_start"]) if request.get("time_start") is not None else None,
        retries=int(request["retries"]) if request.get("retries") is not None else None,
    )


def _collect_runs(position: RunPosition, method: str) -> tuple[list[MonitoringRun], int, str | None]:
    payload, error = _inspect_payload(method)
    runs: list[MonitoringRun] = []
    workers_seen = len(payload)
    for worker, items in payload.items():
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            run = _normalise_run(position, str(worker), raw)
            if run is not None:
                runs.append(run)
    return runs, workers_seen, error


@router.get("/runs", response_model=MonitoringRunsResponse)
def list_runs() -> MonitoringRunsResponse:
    active, active_workers, active_error = _collect_runs("active", "active")
    reserved, reserved_workers, reserved_error = _collect_runs("reserved", "reserved")
    scheduled, scheduled_workers, scheduled_error = _collect_runs("scheduled", "scheduled")
    errors = [err for err in (active_error, reserved_error, scheduled_error) if err]
    return MonitoringRunsResponse(
        generated_at=datetime.utcnow(),
        workers_seen=max(active_workers, reserved_workers, scheduled_workers),
        active=active,
        reserved=reserved,
        scheduled=scheduled,
        totals={
            "active": len(active),
            "reserved": len(reserved),
            "scheduled": len(scheduled),
            "queued": len(reserved) + len(scheduled),
            "all": len(active) + len(reserved) + len(scheduled),
        },
        errors=errors,
    )


@router.post("/runs/{task_id}/revoke")
def revoke_run(task_id: str, req: RevokeRunRequest) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"terminate": bool(req.terminate)}
    if req.terminate:
        kwargs["signal"] = req.signal
    celery_app.control.revoke(task_id, **kwargs)
    return {
        "task_id": task_id,
        "revoked": True,
        "terminate": bool(req.terminate),
        "state": celery_app.AsyncResult(task_id).state,
    }
