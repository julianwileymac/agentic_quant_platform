"""``/dataset-presets`` REST surface.

Exposes the curated dataset preset library and a one-click ingestion
endpoint that dispatches the matching Celery task.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.data.dataset_presets import (
    DatasetPreset,
    list_presets,
    list_preset_names,
    list_presets_by_tag,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dataset-presets", tags=["dataset-presets"])


class PresetView(BaseModel):
    name: str
    description: str
    namespace: str
    table: str
    iceberg_identifier: str
    source_kind: str
    ingestion_task: str
    requires_api_key: bool = False
    api_key_env_var: str | None = None
    default_symbols: list[str] = Field(default_factory=list)
    interval: str = "1d"
    schedule_cron: str | None = None
    documentation_url: str | None = None
    tags: list[str] = Field(default_factory=list)


def _to_view(p: DatasetPreset) -> PresetView:
    return PresetView(**p.to_dict())


@router.get("/", response_model=list[PresetView])
def list_dataset_presets(tag: str | None = None) -> list[PresetView]:
    """Enumerate all curated dataset presets, optionally filtered by tag."""
    presets = list_presets_by_tag(tag) if tag else list_presets()
    return [_to_view(p) for p in presets]


@router.get("/{name}", response_model=PresetView)
def get_dataset_preset(name: str) -> PresetView:
    if name not in list_preset_names():
        raise HTTPException(status_code=404, detail=f"unknown preset: {name}")
    from aqp.data.dataset_presets import get_preset
    return _to_view(get_preset(name))


class IngestRequest(BaseModel):
    symbols: list[str] | None = None
    extra_kwargs: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    task_id: str
    preset: str
    status: str = "queued"


@router.post("/{name}/ingest", response_model=IngestResponse)
def trigger_preset_ingest(name: str, body: IngestRequest | None = None) -> IngestResponse:
    """Dispatch the Celery ingestion task for a preset."""
    if name not in list_preset_names():
        raise HTTPException(status_code=404, detail=f"unknown preset: {name}")
    body = body or IngestRequest()
    try:
        from aqp.tasks.dataset_preset_tasks import dispatch_preset_ingest
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"task dispatch unavailable: {exc}") from exc
    kwargs = dict(body.extra_kwargs)
    if body.symbols is not None:
        kwargs["symbols"] = body.symbols
    result = dispatch_preset_ingest(name, **kwargs)
    return IngestResponse(task_id=str(getattr(result, "id", "local")), preset=name)


__all__ = ["router"]
