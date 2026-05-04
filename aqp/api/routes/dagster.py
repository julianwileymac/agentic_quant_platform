"""Dagster proxy endpoints.

Surfaces a small slice of the cluster's Dagster GraphQL state through
AQP's API gateway: list assets, list runs, trigger an asset
materialization. Falls back to the in-process :class:`Definitions`
when the GraphQL endpoint isn't reachable so local dev still works.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dagster", tags=["dagster"])


class TriggerRequest(BaseModel):
    asset_keys: list[list[str]] = Field(
        ..., description="List of asset key path arrays, e.g. [['aqp', 'fred_observations']]"
    )
    run_config: dict[str, Any] = Field(default_factory=dict)


def _graphql_url() -> str | None:
    url = settings.dagster_graphql_url or settings.dagster_webserver_url
    if not url:
        return None
    if url.endswith("/graphql"):
        return url
    return url.rstrip("/") + "/graphql"


def _local_defs() -> Any:
    try:
        from aqp.dagster.definitions import defs

        return defs
    except Exception as exc:  # noqa: BLE001
        logger.debug("local Definitions unavailable: %s", exc)
        return None


@router.get("/status")
def status() -> dict[str, Any]:
    return {
        "graphql_url": _graphql_url(),
        "code_location": settings.dagster_code_location,
        "module_path": settings.dagster_module_path,
        "grpc_host": settings.dagster_grpc_host,
        "grpc_port": settings.dagster_grpc_port,
    }


@router.get("/assets")
def list_assets() -> dict[str, Any]:
    """List asset keys exposed by the AQP code location.

    Tries the GraphQL endpoint first; falls back to introspecting the
    in-process ``Definitions`` so local dev surfaces the same list.
    """
    url = _graphql_url()
    if url:
        query = (
            "query { assetNodes { assetKey { path } description groupName "
            "computeKind isPartitioned } }"
        )
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json={"query": query})
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return {
                    "source": "graphql",
                    "asset_nodes": data.get("assetNodes", []),
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("dagster graphql assets fetch failed: %s", exc)

    defs = _local_defs()
    if defs is None:
        return {"source": "fallback", "asset_nodes": []}
    asset_nodes: list[dict[str, Any]] = []
    for asset in getattr(defs, "get_asset_graph", lambda: None)() or []:
        try:
            asset_nodes.append(
                {
                    "key": list(asset.key.path),
                    "description": getattr(asset, "description", None),
                    "group_name": getattr(asset, "group_name", None),
                }
            )
        except Exception:  # noqa: BLE001
            continue
    if not asset_nodes:
        # Older Dagster API: walk defs._assets directly.
        for asset in getattr(defs, "_assets_defs", []) or []:
            for key in getattr(asset, "keys", []) or []:
                asset_nodes.append({"key": list(key.path)})
    return {"source": "in_process", "asset_nodes": asset_nodes}


@router.get("/runs")
def list_runs(limit: int = 25) -> dict[str, Any]:
    url = _graphql_url()
    if not url:
        return {"runs": [], "source": "no_graphql"}
    query = (
        "query Runs($limit: Int!) { runsOrError(limit: $limit) { ... on Runs { results "
        "{ runId pipelineName status startTime endTime } } } }"
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                url,
                json={"query": query, "variables": {"limit": limit}},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {
                "source": "graphql",
                "runs": data.get("runsOrError", {}).get("results", []),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("dagster runs fetch failed: %s", exc)
        return {"source": "graphql_error", "runs": [], "error": str(exc)}


@router.post("/trigger")
def trigger_assets(payload: TriggerRequest) -> dict[str, Any]:
    """Trigger a materialization of one or more assets via the GraphQL endpoint."""
    url = _graphql_url()
    if not url:
        raise HTTPException(
            status_code=503,
            detail="Dagster GraphQL endpoint not configured (AQP_DAGSTER_GRAPHQL_URL).",
        )
    mutation = (
        "mutation Materialize($selector: AssetGroupSelector!, $runConfig: RunConfigData) {"
        " launchPipelineExecution(executionParams: {"
        " selector: $selector, runConfigData: $runConfig"
        "}) { __typename ... on LaunchRunSuccess { run { runId } } } }"
    )
    selector = {
        "repositoryLocationName": settings.dagster_code_location,
        "repositoryName": settings.dagster_code_location,
        "assetSelection": [{"path": key} for key in payload.asset_keys],
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                url,
                json={
                    "query": mutation,
                    "variables": {"selector": selector, "runConfig": payload.run_config},
                },
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("dagster trigger failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Schedules and sensors
# ---------------------------------------------------------------------------
def _graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    url = _graphql_url()
    if not url:
        raise HTTPException(
            status_code=503,
            detail="Dagster GraphQL endpoint not configured.",
        )
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json={"query": query, "variables": variables or {}})
            resp.raise_for_status()
            return resp.json().get("data") or {}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/schedules")
def list_schedules() -> dict[str, Any]:
    """List Dagster schedules + their status."""
    query = (
        "query { schedulesOrError { __typename ... on Schedules { results { name "
        "cronSchedule executionTimezone scheduleState { status } } } } }"
    )
    data = _graphql(query)
    schedules = (data.get("schedulesOrError") or {}).get("results") or []
    return {"schedules": schedules}


@router.post("/schedules/{name}/start")
def start_schedule(name: str) -> dict[str, Any]:
    mutation = (
        "mutation Start($name: String!) { startSchedule(scheduleSelector: "
        "{ scheduleName: $name, repositoryName: \"__repository__\", "
        "repositoryLocationName: \"__repository__\" }) { __typename } }"
    )
    return _graphql(mutation, {"name": name})


@router.post("/schedules/{name}/stop")
def stop_schedule(name: str) -> dict[str, Any]:
    mutation = (
        "mutation Stop($name: String!) { stopRunningSchedule(scheduleOriginId: $name) { __typename } }"
    )
    return _graphql(mutation, {"name": name})


@router.get("/sensors")
def list_sensors() -> dict[str, Any]:
    query = (
        "query { sensorsOrError { __typename ... on Sensors { results { name "
        "sensorState { status } } } } }"
    )
    data = _graphql(query)
    return {"sensors": (data.get("sensorsOrError") or {}).get("results") or []}


@router.post("/sensors/{name}/start")
def start_sensor(name: str) -> dict[str, Any]:
    mutation = (
        "mutation Start($name: String!) { startSensor(sensorSelector: "
        "{ sensorName: $name, repositoryName: \"__repository__\", "
        "repositoryLocationName: \"__repository__\" }) { __typename } }"
    )
    return _graphql(mutation, {"name": name})


@router.post("/sensors/{name}/stop")
def stop_sensor(name: str) -> dict[str, Any]:
    mutation = (
        "mutation Stop($name: String!) { stopSensor(jobOriginId: $name) { __typename } }"
    )
    return _graphql(mutation, {"name": name})
