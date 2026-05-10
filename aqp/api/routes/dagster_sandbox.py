"""Interactive Dagster sandbox REST surface (data fabric phase 3)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.api.schemas import TaskAccepted
from aqp.auth.context import RequestContext
from aqp.auth.deps import current_context
from aqp.dagster.sandbox import SandboxRuntime
from aqp.persistence.db import get_session

router = APIRouter(prefix="/dagster/sandbox", tags=["dagster", "sandbox"])


class CreateSessionRequest(BaseModel):
    ttl_minutes: int = Field(default=60, ge=1, le=720)


class SessionSummary(BaseModel):
    id: str
    owner: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    components: list[str] = Field(default_factory=list)
    asset_keys: list[list[str]] = Field(default_factory=list)
    last_run_id: str | None = None
    log_summary: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "open"


class WriteComponentRequest(BaseModel):
    name: str
    body: str


class LoadAirbyteRequest(BaseModel):
    airbyte_connection_id: str


def _summary(runtime: SandboxRuntime) -> SessionSummary:
    return SessionSummary(**runtime.session.to_summary())


@router.post("/sessions", response_model=SessionSummary, status_code=201)
def create_session(
    payload: CreateSessionRequest,
    ctx: RequestContext = Depends(current_context),
) -> SessionSummary:
    runtime = SandboxRuntime.create_session(
        owner=ctx.user_id,
        workspace_id=ctx.workspace_id,
        project_id=ctx.project_id,
        ttl_minutes=payload.ttl_minutes,
    )
    _persist_session(runtime)
    return _summary(runtime)


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions() -> list[SessionSummary]:
    return [SessionSummary(**s.to_summary()) for s in SandboxRuntime.list_sessions()]


@router.get("/sessions/{session_id}", response_model=SessionSummary)
def get_session_view(session_id: str) -> SessionSummary:
    runtime = SandboxRuntime.get(session_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="sandbox session not found")
    return _summary(runtime)


@router.post("/sessions/{session_id}/components", response_model=SessionSummary)
def write_component(session_id: str, payload: WriteComponentRequest) -> SessionSummary:
    runtime = SandboxRuntime.get(session_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="sandbox session not found")
    runtime.write_component(payload.name, payload.body)
    _persist_session(runtime)
    return _summary(runtime)


@router.post("/sessions/{session_id}/airbyte", response_model=SessionSummary)
def write_airbyte(
    session_id: str,
    payload: LoadAirbyteRequest,
) -> SessionSummary:
    from aqp.persistence.models_airbyte import AirbyteConnectionRow

    runtime = SandboxRuntime.get(session_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="sandbox session not found")
    with get_session() as session:
        row = session.execute(
            select(AirbyteConnectionRow)
            .where(AirbyteConnectionRow.id == payload.airbyte_connection_id)
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"airbyte connection {payload.airbyte_connection_id!r} not found",
            )
        connection_payload = {
            "name": row.name,
            "source_connector_id": row.source_connector_id,
            "destination_connector_id": row.destination_connector_id,
            "streams": row.streams or [],
        }
    runtime.write_airbyte_connection(connection_payload)
    _persist_session(runtime)
    return _summary(runtime)


@router.post("/sessions/{session_id}/load", response_model=SessionSummary)
def load_session(session_id: str) -> SessionSummary:
    runtime = SandboxRuntime.get(session_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="sandbox session not found")
    runtime.load()
    _persist_session(runtime)
    return _summary(runtime)


@router.post("/sessions/{session_id}/execute", response_model=TaskAccepted)
def execute_session(session_id: str) -> TaskAccepted:
    runtime = SandboxRuntime.get(session_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="sandbox session not found")
    from aqp.tasks.dagster_sandbox_tasks import execute_sandbox_session

    async_result = execute_sandbox_session.delay(session_id)
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.delete("/sessions/{session_id}")
def teardown_session(session_id: str) -> dict[str, Any]:
    runtime = SandboxRuntime.get(session_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="sandbox session not found")
    result = runtime.teardown()
    _persist_teardown(session_id)
    return result


@router.post("/janitor")
def run_janitor() -> dict[str, Any]:
    dropped = SandboxRuntime.janitor()
    return {"dropped": dropped, "count": len(dropped)}


# ---------------------------------------------------------------- persistence


def _persist_session(runtime: SandboxRuntime) -> None:
    try:
        from aqp.persistence.models_dagster_sandbox import (  # type: ignore[import-not-found]
            DagsterSandboxSessionRow,
        )

        with get_session() as session:
            row = session.execute(
                select(DagsterSandboxSessionRow)
                .where(DagsterSandboxSessionRow.id == runtime.session.id)
                .limit(1)
            ).scalar_one_or_none()
            payload = runtime.session.to_summary()
            if row is None:
                row = DagsterSandboxSessionRow(
                    id=runtime.session.id,
                    owner_user_id=runtime.session.owner,
                    workspace_id=runtime.session.workspace_id,
                    project_id=runtime.session.project_id,
                    status=payload["status"],
                    components_json=runtime.session.components,
                    log_summary_json=payload["log_summary"],
                    last_run_id=payload["last_run_id"],
                    expires_at=runtime.session.expires_at,
                )
                session.add(row)
            else:
                row.status = payload["status"]
                row.components_json = dict(runtime.session.components)
                row.log_summary_json = list(payload["log_summary"])
                row.last_run_id = payload["last_run_id"]
                row.expires_at = runtime.session.expires_at
                session.add(row)
            session.commit()
    except Exception:  # noqa: BLE001
        # Persistence is best-effort; the session lives in-memory either way.
        pass


def _persist_teardown(session_id: str) -> None:
    try:
        from aqp.persistence.models_dagster_sandbox import (  # type: ignore[import-not-found]
            DagsterSandboxSessionRow,
        )

        with get_session() as session:
            row = session.execute(
                select(DagsterSandboxSessionRow)
                .where(DagsterSandboxSessionRow.id == session_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is not None:
                row.status = "closed"
                session.add(row)
                session.commit()
    except Exception:  # noqa: BLE001
        pass
