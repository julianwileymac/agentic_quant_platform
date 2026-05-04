"""Small Airbyte-compatible dev server for local AQP compose.

This is not a replacement for production Airbyte. It gives local AQP a
reachable Airbyte API surface for health, metadata sync, and UI wiring until a
real Airbyte deployment URL/token is supplied.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI

app = FastAPI(title="AQP Airbyte Dev Server", version="0.1.0")

_WORKSPACE_ID = "local-aqp-workspace"


def _workspace() -> dict[str, Any]:
    return {
        "workspaceId": _WORKSPACE_ID,
        "id": _WORKSPACE_ID,
        "name": "AQP Local Workspace",
        "createdAt": "2026-01-01T00:00:00Z",
    }


@app.get("/health")
@app.get("/api/v1/health")
@app.get("/api/public/v1/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "available": True,
        "mode": "aqp-dev",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/public/v1/workspaces")
def list_workspaces() -> dict[str, Any]:
    return {"workspaces": [_workspace()], "data": [_workspace()]}


@app.get("/api/public/v1/sources")
def list_sources() -> dict[str, Any]:
    return {"sources": [], "data": []}


@app.get("/api/public/v1/destinations")
def list_destinations() -> dict[str, Any]:
    return {"destinations": [], "data": []}


@app.get("/api/public/v1/connections")
def list_connections() -> dict[str, Any]:
    return {"connections": [], "data": []}


@app.post("/api/public/v1/sources/{source_id}/discover_schema")
@app.post("/api/v1/sources/{source_id}/discover_schema")
@app.post("/api/v1/sources/discover_schema")
def discover_schema(source_id: str | None = None) -> dict[str, Any]:
    return {"catalog": {"streams": []}, "sourceId": source_id}


@app.post("/api/public/v1/jobs")
def create_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = f"local-{int(datetime.utcnow().timestamp())}"
    return {"jobId": job_id, "id": job_id, "status": "succeeded", "job": {"id": job_id, "status": "succeeded"}, "request": payload}


@app.get("/api/public/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return {"jobId": job_id, "id": job_id, "status": "succeeded", "job": {"id": job_id, "status": "succeeded"}}

