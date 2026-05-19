"""Dagster proxy endpoints.

Surfaces a small slice of the cluster's Dagster GraphQL state through
AQP's API gateway: list assets, list runs, trigger an asset
materialization. Endpoint behavior is GraphQL-first with strict
error surfacing to avoid stale local fallbacks.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Callable

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
from aqp.config import settings

logger = logging.getLogger(__name__)
router = secure_router(prefix="/dagster", tags=["dagster"], default_scope="read:infrastructure")


class TriggerRequest(BaseModel):
    asset_keys: list[list[str]] = Field(
        ...,
        min_length=1,
        description="List of asset key path arrays, e.g. [['aqp', 'fred_observations']]",
    )
    run_config: dict[str, Any] = Field(default_factory=dict)


_GRAPHQL_TIMEOUT_SECONDS = 10.0
_SELECTOR_ERROR_HINTS = (
    "repository",
    "selector",
    "location",
    "asset job",
    "could not find",
)


def _graphql_url() -> str | None:
    url = settings.dagster_graphql_url or settings.dagster_webserver_url
    if not url:
        return None
    if url.endswith("/graphql"):
        return url
    return url.rstrip("/") + "/graphql"


def _format_graphql_errors(errors: Any) -> str:
    if not isinstance(errors, list):
        return str(errors)
    chunks: list[str] = []
    for error in errors:
        if isinstance(error, dict):
            message = str(error.get("message") or "unknown dagster graphql error").strip()
            path = error.get("path")
            if isinstance(path, list) and path:
                message = f"{message} (path={'.'.join(str(part) for part in path)})"
            chunks.append(message)
        else:
            chunks.append(str(error))
    return "; ".join(chunk for chunk in chunks if chunk) or "unknown dagster graphql error"


def _post_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    url = _graphql_url()
    if not url:
        raise HTTPException(
            status_code=503,
            detail="Dagster GraphQL endpoint not configured.",
        )
    payload = {"query": query, "variables": variables or {}}
    try:
        with httpx.Client(timeout=_GRAPHQL_TIMEOUT_SECONDS) as client:
            resp = client.post(url, json=payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Dagster GraphQL request failed: {exc}") from exc

    response_text = resp.text
    try:
        response_payload = resp.json()
    except ValueError:
        response_payload = {}

    if resp.is_error:
        detail = response_payload or response_text
        logger.warning(
            "dagster graphql http error status=%s body=%s",
            resp.status_code,
            str(detail)[:2000],
        )
        raise HTTPException(
            status_code=502,
            detail=f"Dagster GraphQL {resp.status_code}: {detail}",
        )

    if not isinstance(response_payload, dict):
        raise HTTPException(
            status_code=502,
            detail=f"Dagster GraphQL returned non-object payload: {response_text[:500]}",
        )
    errors = response_payload.get("errors")
    if errors:
        formatted_errors = _format_graphql_errors(errors)
        logger.warning("dagster graphql errors: %s", formatted_errors[:2000])
        raise HTTPException(status_code=502, detail=f"Dagster GraphQL errors: {formatted_errors}")
    return response_payload


@lru_cache(maxsize=1)
def _repository_selector() -> dict[str, str]:
    """Resolve the active Dagster repository selector for this code location."""

    query = (
        "query { workspaceOrError { __typename ... on Workspace { locationEntries { "
        "name locationOrLoadError { __typename ... on RepositoryLocation { repositories { name } } "
        "... on PythonError { message } } } } ... on PythonError { message } } }"
    )
    fallback = {
        "repositoryLocationName": settings.dagster_code_location,
        "repositoryName": settings.dagster_code_location,
    }
    try:
        payload = _post_graphql(query)
        entries = (
            payload.get("data", {})
            .get("workspaceOrError", {})
            .get("locationEntries", [])
        )
    except HTTPException:
        logger.warning("falling back to configured Dagster repository selector")
        return fallback

    candidates: list[dict[str, str]] = []
    for entry in entries:
        location_name = entry.get("name")
        location = entry.get("locationOrLoadError") or {}
        for repo in location.get("repositories") or []:
            repo_name = repo.get("name")
            if location_name and repo_name:
                candidates.append(
                    {
                        "repositoryLocationName": str(location_name),
                        "repositoryName": str(repo_name),
                    }
                )

    if not candidates:
        return fallback

    preferred_names = {
        settings.dagster_code_location,
        settings.dagster_module_path,
        "aqp",
        "__repository__",
    }
    for candidate in candidates:
        if (
            candidate["repositoryLocationName"] in preferred_names
            or candidate["repositoryName"] in preferred_names
        ):
            return candidate
    return candidates[0]


def _validate_repository_selector(selector: dict[str, Any]) -> dict[str, str]:
    location = str(selector.get("repositoryLocationName") or "").strip()
    repository = str(selector.get("repositoryName") or "").strip()
    if not location or not repository:
        raise HTTPException(
            status_code=502,
            detail=f"Dagster repository selector invalid: {selector}",
        )
    return {
        "repositoryLocationName": location,
        "repositoryName": repository,
    }


def _repository_selector_checked(*, force_refresh: bool = False) -> dict[str, str]:
    if force_refresh:
        _repository_selector.cache_clear()
    return _validate_repository_selector(_repository_selector())


def _is_selector_error(detail: Any) -> bool:
    lowered = str(detail).lower()
    return any(hint in lowered for hint in _SELECTOR_ERROR_HINTS)


def _run_with_selector_retry(
    operation: str,
    callback: Callable[[dict[str, str]], dict[str, Any]],
) -> dict[str, Any]:
    selector = _repository_selector_checked()
    try:
        return callback(selector)
    except HTTPException as exc:
        if not _is_selector_error(exc.detail):
            raise
        logger.warning(
            "dagster selector stale during %s; refreshing selector cache",
            operation,
        )
        selector = _repository_selector_checked(force_refresh=True)
        return callback(selector)


@router.get("/status")
def status() -> dict[str, Any]:
    repository_selector: dict[str, str] = {}
    selector_error: str | None = None
    try:
        repository_selector = _repository_selector_checked()
    except HTTPException as exc:
        selector_error = str(exc.detail)
    return {
        "graphql_url": _graphql_url(),
        "code_location": settings.dagster_code_location,
        "module_path": settings.dagster_module_path,
        "grpc_host": settings.dagster_grpc_host,
        "grpc_port": settings.dagster_grpc_port,
        "repository_selector": repository_selector,
        "repository_selector_error": selector_error,
    }


@router.get("/assets")
def list_assets() -> dict[str, Any]:
    """List asset keys exposed by the active Dagster GraphQL endpoint."""
    query = (
        "query { assetNodes { assetKey { path } description groupName "
        "computeKind isPartitioned } }"
    )
    data = _graphql(query)
    return {
        "source": "graphql",
        "asset_nodes": data.get("assetNodes") or [],
    }


@router.get("/runs")
def list_runs(limit: int = 25) -> dict[str, Any]:
    query = (
        "query Runs($limit: Int!) { runsOrError(limit: $limit) { ... on Runs { results "
        "{ runId pipelineName status startTime endTime } } } }"
    )
    data = _graphql(query, {"limit": limit})
    return {
        "source": "graphql",
        "runs": (data.get("runsOrError") or {}).get("results") or [],
    }


def _validate_asset_keys(asset_keys: list[list[str]]) -> list[list[str]]:
    validated: list[list[str]] = []
    for idx, key_path in enumerate(asset_keys):
        if not key_path:
            raise HTTPException(status_code=422, detail=f"asset_keys[{idx}] cannot be empty")
        cleaned_path: list[str] = []
        for part in key_path:
            text = str(part).strip()
            if not text:
                raise HTTPException(
                    status_code=422,
                    detail=f"asset_keys[{idx}] contains an empty key segment",
                )
            cleaned_path.append(text)
        validated.append(cleaned_path)
    return validated


@router.post("/trigger")
def trigger_assets(payload: TriggerRequest) -> dict[str, Any]:
    """Trigger a materialization of one or more assets via the GraphQL endpoint."""
    asset_keys = _validate_asset_keys(payload.asset_keys)
    mutation = (
        "mutation Materialize($selector: JobOrPipelineSelector!, $runConfig: RunConfigData) {"
        " launchPipelineExecution(executionParams: {"
        " selector: $selector, runConfigData: $runConfig"
        "}) { __typename ... on LaunchRunSuccess { run { runId } } } }"
    )
    def _launch(selector: dict[str, str]) -> dict[str, Any]:
        payload_selector = {
            **selector,
            "jobName": "__ASSET_JOB",
            "assetSelection": [{"path": key} for key in asset_keys],
        }
        return _post_graphql(
            mutation,
            {"selector": payload_selector, "runConfig": payload.run_config},
        )

    return _run_with_selector_retry("trigger assets", _launch)


# ---------------------------------------------------------------------------
# Schedules and sensors
# ---------------------------------------------------------------------------
def _graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    response = _post_graphql(query, variables)
    data = response.get("data")
    if data is None:
        raise HTTPException(status_code=502, detail="Dagster GraphQL response missing data payload")
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=f"Dagster GraphQL data payload invalid: {data}")
    return data


def _extract_results_or_error(payload: dict[str, Any], field: str) -> list[dict[str, Any]]:
    node = payload.get(field) or {}
    node_type = node.get("__typename")
    if node_type == "PythonError":
        raise HTTPException(
            status_code=502,
            detail=f"Dagster {field} query failed: {node.get('message')}",
        )
    return node.get("results") or []


def _schedule_state(name: str) -> dict[str, Any]:
    query = (
        "query Schedules($selector: RepositorySelector!) { schedulesOrError("
        "repositorySelector: $selector) { __typename ... on Schedules { results { "
        "name scheduleState { id selectorId status } } } ... on PythonError { message } } }"
    )
    def _state(selector: dict[str, str]) -> dict[str, Any]:
        data = _graphql(query, {"selector": selector})
        for schedule in _extract_results_or_error(data, "schedulesOrError"):
            if schedule.get("name") == name:
                return schedule.get("scheduleState") or {}
        raise HTTPException(status_code=404, detail=f"Dagster schedule not found: {name}")

    return _run_with_selector_retry(f"load schedule state {name}", _state)


def _sensor_state(name: str) -> dict[str, Any]:
    query = (
        "query Sensors($selector: RepositorySelector!) { sensorsOrError("
        "repositorySelector: $selector) { __typename ... on Sensors { results { "
        "name sensorState { id selectorId status } } } ... on PythonError { message } } }"
    )
    def _state(selector: dict[str, str]) -> dict[str, Any]:
        data = _graphql(query, {"selector": selector})
        for sensor in _extract_results_or_error(data, "sensorsOrError"):
            if sensor.get("name") == name:
                return sensor.get("sensorState") or {}
        raise HTTPException(status_code=404, detail=f"Dagster sensor not found: {name}")

    return _run_with_selector_retry(f"load sensor state {name}", _state)


@router.get("/schedules")
def list_schedules() -> dict[str, Any]:
    """List Dagster schedules + their status."""
    query = (
        "query Schedules($selector: RepositorySelector!) { schedulesOrError("
        "repositorySelector: $selector) { __typename ... on Schedules { results { name "
        "cronSchedule executionTimezone scheduleState { id selectorId status } } } "
        "... on PythonError { message } } }"
    )
    def _list(selector: dict[str, str]) -> dict[str, Any]:
        data = _graphql(query, {"selector": selector})
        return {"schedules": _extract_results_or_error(data, "schedulesOrError")}

    return _run_with_selector_retry("list schedules", _list)


@router.post("/schedules/{name}/start")
def start_schedule(name: str) -> dict[str, Any]:
    mutation = (
        "mutation Start($selector: ScheduleSelector!) { startSchedule("
        "scheduleSelector: $selector) { __typename } }"
    )
    def _start(selector: dict[str, str]) -> dict[str, Any]:
        schedule_selector = {**selector, "scheduleName": name}
        return _graphql(mutation, {"selector": schedule_selector})

    return _run_with_selector_retry(f"start schedule {name}", _start)


@router.post("/schedules/{name}/stop")
def stop_schedule(name: str) -> dict[str, Any]:
    state = _schedule_state(name)
    schedule_id = state.get("id")
    selector_id = state.get("selectorId")
    if not schedule_id and not selector_id:
        raise HTTPException(
            status_code=502,
            detail=f"Dagster schedule state missing id/selectorId: {name}",
        )
    mutation = (
        "mutation Stop($id: String, $selectorId: String) { stopRunningSchedule("
        "id: $id, scheduleSelectorId: $selectorId) { __typename } }"
    )
    return _graphql(mutation, {"id": schedule_id, "selectorId": selector_id})


@router.get("/sensors")
def list_sensors() -> dict[str, Any]:
    query = (
        "query Sensors($selector: RepositorySelector!) { sensorsOrError("
        "repositorySelector: $selector) { __typename ... on Sensors { results { name "
        "sensorState { id selectorId status } } } ... on PythonError { message } } }"
    )
    def _list(selector: dict[str, str]) -> dict[str, Any]:
        data = _graphql(query, {"selector": selector})
        return {"sensors": _extract_results_or_error(data, "sensorsOrError")}

    return _run_with_selector_retry("list sensors", _list)


@router.post("/sensors/{name}/start")
def start_sensor(name: str) -> dict[str, Any]:
    mutation = (
        "mutation Start($selector: SensorSelector!) { startSensor("
        "sensorSelector: $selector) { __typename } }"
    )
    def _start(selector: dict[str, str]) -> dict[str, Any]:
        sensor_selector = {**selector, "sensorName": name}
        return _graphql(mutation, {"selector": sensor_selector})

    return _run_with_selector_retry(f"start sensor {name}", _start)


@router.post("/sensors/{name}/stop")
def stop_sensor(name: str) -> dict[str, Any]:
    state = _sensor_state(name)
    sensor_id = state.get("id")
    selector_id = state.get("selectorId")
    if not sensor_id and not selector_id:
        raise HTTPException(
            status_code=502,
            detail=f"Dagster sensor state missing id/selectorId: {name}",
        )
    mutation = (
        "mutation Stop($id: String, $selectorId: String) { stopSensor("
        "id: $id, jobSelectorId: $selectorId) { __typename } }"
    )
    return _graphql(mutation, {"id": sensor_id, "selectorId": selector_id})
