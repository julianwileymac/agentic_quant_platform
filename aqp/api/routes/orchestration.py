"""Data-fabric orchestration routes (Airbyte + Dagster)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from aqp.api.security import require_authenticated
from aqp.data.airbyte.orchestrator import AirbyteOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["orchestration"],
    dependencies=[Depends(require_authenticated)],
)


class AirbyteSyncRequest(BaseModel):
    connection_id: str
    cursor_override: datetime | None = None


class DagsterMaterializeRequest(BaseModel):
    asset_keys: list[str] = Field(default_factory=list, min_length=1)
    partition_keys: list[str] | None = None


def _asset_definition_keys(asset_def: Any) -> set[str]:
    keys: set[str] = set()
    key = getattr(asset_def, "key", None)
    if key is not None:
        path = getattr(key, "path", None)
        if path:
            keys.add(".".join(str(part) for part in path))
    key_set = getattr(asset_def, "keys", None)
    if key_set is not None:
        for item in key_set:
            path = getattr(item, "path", None)
            if path:
                keys.add(".".join(str(part) for part in path))
    return keys


def _normalize_asset_key(value: str) -> str:
    return ".".join(part for part in str(value).replace("/", ".").split(".") if part)


@router.post("/airbyte/sync")
def airbyte_sync(payload: AirbyteSyncRequest) -> dict[str, str]:
    orchestrator = AirbyteOrchestrator()
    try:
        job_id = orchestrator.trigger_sync(
            payload.connection_id,
            payload.cursor_override,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Airbyte sync trigger failed: {exc}",
        ) from exc
    return {"job_id": str(job_id)}


@router.get("/airbyte/sync/{job_id}")
def airbyte_sync_status(job_id: str) -> dict[str, str]:
    orchestrator = AirbyteOrchestrator()
    try:
        status_value = orchestrator.poll_sync_status(job_id, timeout_s=0)
    except TimeoutError:
        status_value = "running"
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Airbyte sync status failed: {exc}",
        ) from exc
    return {"status": str(status_value)}


@router.post("/dagster/materialize")
def dagster_materialize(payload: DagsterMaterializeRequest) -> dict[str, Any]:
    try:
        import dagster as dg
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dagster is not installed on this API runtime",
        ) from exc

    try:
        from aqp.dagster.assets import all_assets
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dagster assets registry unavailable: {exc}",
        ) from exc

    requested = {_normalize_asset_key(item) for item in payload.asset_keys}
    if not requested:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="asset_keys must include at least one non-empty key",
        )

    selected_assets: list[Any] = []
    for asset_def in all_assets():
        keys = _asset_definition_keys(asset_def)
        if not keys:
            continue
        if keys & requested:
            selected_assets.append(asset_def)
            continue
        terminal_names = {key.rpartition(".")[2] for key in keys}
        if terminal_names & requested:
            selected_assets.append(asset_def)

    if not selected_assets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Dagster assets matched keys: {sorted(requested)}",
        )

    partition_key = None
    if payload.partition_keys:
        partition_key = str(payload.partition_keys[0]).strip() or None

    try:
        if partition_key is None:
            result = dg.materialize(selected_assets)
        else:
            result = dg.materialize(selected_assets, partition_key=partition_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dagster materialize failed: {exc}",
        ) from exc

    selected_keys: list[str] = []
    for asset_def in selected_assets:
        selected_keys.extend(sorted(_asset_definition_keys(asset_def)))
    return {
        "ok": bool(getattr(result, "success", False)),
        "status": "success" if bool(getattr(result, "success", False)) else "failed",
        "run_id": str(getattr(result, "run_id", "") or ""),
        "asset_keys": sorted(set(selected_keys)),
    }


__all__ = ["AirbyteSyncRequest", "DagsterMaterializeRequest", "router"]
