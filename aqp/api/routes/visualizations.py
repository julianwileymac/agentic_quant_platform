"""Visualization layer routes for Superset and Bokeh."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted
from aqp.config import settings
from aqp.data import iceberg_catalog
from aqp.services.trino_probe import probe_trino_coordinator
from aqp.data.dataset_presets import PRESETS
from aqp.services.superset_client import SupersetClient
from aqp.visualization.bokeh_renderer import BokehChartSpec, clear_cache, render_bokeh_item
from aqp.visualization.superset_assets import preset_for_identifier
from aqp.visualization.superset_sync import build_current_asset_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/visualizations", tags=["visualizations"])


class GuestTokenRequest(BaseModel):
    dashboard_uuid: str | None = None
    rls: list[dict[str, str]] = Field(default_factory=list)


class GuestTokenResponse(BaseModel):
    token: str
    dashboard_uuid: str
    superset_url: str


class BokehRenderResponse(BaseModel):
    item: dict[str, Any]


@router.get("/config")
def visualization_config() -> dict[str, Any]:
    return {
        "superset_url": settings.superset_public_url or settings.superset_base_url,
        "superset_base_url": settings.superset_base_url,
        "trino_uri": settings.trino_uri,
        "trino_catalog": settings.trino_catalog,
        "trino_schema": settings.trino_schema,
        "trino_http_url": settings.trino_http_url or None,
        "default_dashboard_uuid": settings.superset_default_dashboard_uuid,
        "cache_ttl_seconds": settings.visualization_cache_ttl_seconds,
    }


@router.get("/trino/health")
def trino_health() -> dict[str, Any]:
    """Coordinator reachability for the Trino instance implied by ``AQP_TRINO_URI``."""
    return probe_trino_coordinator()


@router.get("/superset/assets")
def superset_asset_plan() -> dict[str, Any]:
    return build_current_asset_plan().to_dict()


@router.post("/superset/sync", response_model=TaskAccepted)
def sync_superset() -> TaskAccepted:
    from aqp.tasks.visualization_tasks import sync_superset_assets_task

    task = sync_superset_assets_task.delay()
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/tasks/{task.id}")


@router.post("/superset/guest-token", response_model=GuestTokenResponse)
def superset_guest_token(req: GuestTokenRequest) -> GuestTokenResponse:
    dashboard_uuid = (req.dashboard_uuid or settings.superset_default_dashboard_uuid).strip()
    if not dashboard_uuid:
        raise HTTPException(400, "dashboard_uuid is required until AQP_SUPERSET_DEFAULT_DASHBOARD_UUID is set")
    try:
        with SupersetClient() as client:
            token = client.create_guest_token(
                resources=[{"type": "dashboard", "id": dashboard_uuid}],
                rls=req.rls,
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Superset guest token failed: {exc}") from exc
    return GuestTokenResponse(
        token=token,
        dashboard_uuid=dashboard_uuid,
        superset_url=settings.superset_public_url or settings.superset_base_url,
    )


@router.post("/bokeh/render", response_model=BokehRenderResponse)
def render_bokeh(spec: BokehChartSpec) -> BokehRenderResponse:
    try:
        return BokehRenderResponse(item=render_bokeh_item(spec))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Bokeh render failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Iceberg dataset discovery surface used by the interactive Bokeh explorer.
# ---------------------------------------------------------------------------


class DatasetSummary(BaseModel):
    identifier: str
    schema: str
    table: str
    label: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    has_preset: bool = False


class DatasetColumn(BaseModel):
    name: str
    dtype: str = ""


class DatasetColumnsResponse(BaseModel):
    identifier: str
    columns: list[DatasetColumn]


@router.get("/datasets")
def list_visualization_datasets() -> dict[str, list[DatasetSummary]]:
    """Return the Iceberg tables available for Bokeh / Superset rendering."""

    try:
        identifiers = iceberg_catalog.list_tables()
    except Exception as exc:  # noqa: BLE001
        logger.warning("iceberg list_tables failed in /visualizations/datasets: %s", exc)
        identifiers = []

    out: list[DatasetSummary] = []
    for identifier in identifiers:
        namespace, _, table_name = identifier.partition(".")
        preset = preset_for_identifier(identifier)
        out.append(
            DatasetSummary(
                identifier=identifier,
                schema=namespace,
                table=table_name,
                label=preset.name.replace("_", " ").title() if preset else identifier,
                description=preset.description if preset else "",
                tags=list(preset.tags) if preset else [],
                has_preset=preset is not None,
            )
        )

    # Always surface every preset so the explorer can hint at datasets the
    # user can ingest on demand, marked with has_preset=True even when the
    # identifier hasn't materialised yet.
    seen = {row.identifier for row in out}
    for preset in PRESETS.values():
        if preset.iceberg_identifier in seen:
            continue
        out.append(
            DatasetSummary(
                identifier=preset.iceberg_identifier,
                schema=preset.namespace,
                table=preset.table,
                label=preset.name.replace("_", " ").title(),
                description=preset.description,
                tags=list(preset.tags),
                has_preset=True,
            )
        )

    out.sort(key=lambda row: row.identifier)
    return {"datasets": out}


@router.get("/datasets/{identifier}/columns", response_model=DatasetColumnsResponse)
def visualization_dataset_columns(identifier: str) -> DatasetColumnsResponse:
    """Return the column names + dtypes for an Iceberg dataset."""

    try:
        table = iceberg_catalog.load_table(identifier)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"dataset {identifier!r} not loadable: {exc}") from exc
    if table is None:
        raise HTTPException(404, f"dataset {identifier!r} not found in Iceberg catalog")

    columns: list[DatasetColumn] = []
    schema = table.schema()
    for field in getattr(schema, "fields", []):
        name = getattr(field, "name", None)
        dtype_obj = getattr(field, "field_type", None) or getattr(field, "type", None)
        dtype = str(dtype_obj) if dtype_obj is not None else ""
        if name:
            columns.append(DatasetColumn(name=str(name), dtype=dtype))

    return DatasetColumnsResponse(identifier=identifier, columns=columns)


# ---------------------------------------------------------------------------
# Bulk Superset asset bundle export / import + cache management.
# ---------------------------------------------------------------------------


class BundleExportRequest(BaseModel):
    dashboard_ids: list[int] = Field(default_factory=list)
    label: str = Field(default="aqp")


@router.post("/superset/bundle/export", response_model=TaskAccepted)
def export_superset_bundle(req: BundleExportRequest) -> TaskAccepted:
    from aqp.tasks.visualization_tasks import export_superset_bundle_task

    task = export_superset_bundle_task.delay(req.dashboard_ids or None, req.label)
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/tasks/{task.id}")


@router.post("/superset/bundle/import", response_model=TaskAccepted)
async def import_superset_bundle(file: UploadFile) -> TaskAccepted:
    from aqp.tasks.visualization_tasks import import_superset_bundle_task

    payload = await file.read()
    bundle_dir = Path(settings.visualization_bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    target = bundle_dir / (file.filename or "uploaded.zip")
    target.write_bytes(payload)
    task = import_superset_bundle_task.delay(str(target))
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/tasks/{task.id}")


class CacheClearRequest(BaseModel):
    older_than_seconds: int | None = None


class CacheClearResponse(BaseModel):
    file: int
    redis: int


@router.post("/cache/clear", response_model=CacheClearResponse)
def clear_visualization_cache(req: CacheClearRequest | None = None) -> CacheClearResponse:
    summary = clear_cache(older_than_seconds=(req.older_than_seconds if req else None))
    return CacheClearResponse(**summary)


@router.post("/datahub/sync", response_model=TaskAccepted)
def sync_superset_to_datahub() -> TaskAccepted:
    from aqp.tasks.visualization_tasks import push_superset_to_datahub_task

    task = push_superset_to_datahub_task.delay()
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/tasks/{task.id}")
