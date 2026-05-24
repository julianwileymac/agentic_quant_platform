"""Thin proxy in front of Jaeger's HTTP query API.

The management console embeds a "recent traces" widget and individual trace
drill-downs.  Calling Jaeger directly from the browser triggers CORS issues
because the Jaeger query frontend does not advertise CORS headers in the
default deployment.  Routing the requests through the management backend
avoids the issue and lets us layer caching / auth on top later.

Endpoints
---------
* ``GET /api/traces/services`` - list service names known to Jaeger.
* ``GET /api/traces/operations?service=...`` - list operations for a service.
* ``GET /api/traces/search?service=...&limit=...&lookback=1h`` - return recent
  traces.
* ``GET /api/traces/{trace_id}`` - fetch a full trace by ID.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import Settings, get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _jaeger_base(settings: Settings) -> str:
    """Resolve the in-cluster Jaeger query API root."""

    override = getattr(settings, "jaeger_query_url", None)
    if override:
        return override.rstrip("/")
    return "http://jaeger-query.observability.svc.cluster.local:16686"


async def _jaeger_get(settings: Settings, path: str, params: Optional[dict[str, Any]] = None) -> Any:
    url = f"{_jaeger_base(settings)}{path}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        logger.warning("Jaeger proxy GET %s failed: %s", url, exc)
        raise HTTPException(status_code=502, detail=f"jaeger upstream unreachable: {exc}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/services", response_model=dict)
async def list_services(settings: Settings = Depends(get_settings)) -> dict:
    """List service names known to Jaeger."""

    return await _jaeger_get(settings, "/api/services")


@router.get("/operations", response_model=dict)
async def list_operations(
    service: str = Query(..., description="Service name from /traces/services"),
    settings: Settings = Depends(get_settings),
) -> dict:
    """List operation names for a given service."""

    return await _jaeger_get(settings, f"/api/services/{service}/operations")


@router.get("/search", response_model=dict)
async def search_traces(
    service: Optional[str] = Query(None),
    operation: Optional[str] = Query(None),
    tags: Optional[str] = Query(None, description="Jaeger tags JSON object"),
    limit: int = Query(20, ge=1, le=200),
    lookback: str = Query("1h"),
    minDuration: Optional[str] = Query(None),
    maxDuration: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Search recent traces.  Mirrors Jaeger's ``/api/traces`` query string."""

    params: dict[str, Any] = {"limit": limit, "lookback": lookback}
    if service:
        params["service"] = service
    if operation:
        params["operation"] = operation
    if tags:
        params["tags"] = tags
    if minDuration:
        params["minDuration"] = minDuration
    if maxDuration:
        params["maxDuration"] = maxDuration
    return await _jaeger_get(settings, "/api/traces", params)


@router.get("/{trace_id}", response_model=dict)
async def get_trace(trace_id: str, settings: Settings = Depends(get_settings)) -> dict:
    """Fetch a full trace by its ID."""

    return await _jaeger_get(settings, f"/api/traces/{trace_id}")
