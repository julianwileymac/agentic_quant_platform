"""``/manage/timeseries/*`` — QuestDB admin.

Phase 3 of the AQP infra-expansion plan. Read-only proxies to
QuestDB's HTTP API (``/exec``, ``/exp``, ``/status``) for the
frontend admin pages. Mutations / ingest go through the
``data.timeseries.questdb.*`` DataMCP tools in ``aqp/`` so the
agent + admin UI surfaces share one audit-policy path.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services import topology as topology_service

router = APIRouter(tags=["timeseries"], prefix="/timeseries")


def _questdb_http() -> str:
    base = topology_service.resolve_endpoint("questdb", "http")
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "questdb_http_endpoint_unset"},
        )
    return base.rstrip("/")


@router.get(
    "/questdb/status",
    summary="QuestDB process status.",
    response_model=ResponseEnvelope[Any],
)
async def questdb_status(
    user: AuthenticatedUser = Depends(require_scope("read:timeseries")),
) -> ResponseEnvelope[Any]:
    base = _questdb_http()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{base}/status")
    return ResponseEnvelope(
        status="ok",
        data={
            "http_status": resp.status_code,
            "body": resp.text[:512],
        },
    )


@router.get(
    "/questdb/tables",
    summary="List QuestDB tables (via tables() built-in).",
    response_model=ResponseEnvelope[Any],
)
async def questdb_tables(
    user: AuthenticatedUser = Depends(require_scope("read:timeseries")),
) -> ResponseEnvelope[Any]:
    base = _questdb_http()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{base}/exec",
            params={"query": "tables();"},
        )
    return ResponseEnvelope(status="ok", data=resp.json() if resp.text else {})


@router.get(
    "/questdb/partitions",
    summary="QuestDB per-partition info for a single table.",
    response_model=ResponseEnvelope[Any],
)
async def questdb_partitions(
    table: str,
    user: AuthenticatedUser = Depends(require_scope("read:timeseries")),
) -> ResponseEnvelope[Any]:
    base = _questdb_http()
    # The MCP allow-list mirrors here; admin UI lets the operator
    # name a table explicitly so we trust the input but escape via
    # repr() to keep the SQL well-formed (no parameter binding in
    # the QuestDB HTTP API).
    safe_table = repr(table)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{base}/exec",
            params={"query": f"SELECT * FROM table_partitions({safe_table});"},
        )
    return ResponseEnvelope(status="ok", data=resp.json() if resp.text else {})


__all__ = ["router"]
