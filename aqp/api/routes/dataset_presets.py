"""``/dataset-presets`` REST surface.

Exposes the curated dataset preset library and a one-click ingestion
endpoint that dispatches the matching Celery task. Also exposes a
per-preset setup wizard that walks the user through credentials,
sink selection, scheduling, and saving a project-scoped
:class:`DatasetPipelineConfigRow`.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aqp.auth.context import RequestContext
from aqp.auth.deps import current_context
from aqp.data.dataset_presets import (
    DatasetPreset,
    list_presets,
    list_preset_names,
    list_presets_by_tag,
)
from aqp.data.dataset_presets_wizards import (
    WIZARDS as PRESET_WIZARDS,
    get_preset_wizard,
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
    version: int = 1
    setup_steps: list[dict[str, Any]] = Field(default_factory=list)
    required_config: dict[str, Any] = Field(default_factory=dict)
    supported_sinks: list[str] = Field(default_factory=list)
    default_pipeline_manifest: dict[str, Any] = Field(default_factory=dict)


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


# ---------------------------------------------------------------------------
# Per-preset setup wizard
# ---------------------------------------------------------------------------
class WizardStepView(BaseModel):
    id: str
    label: str
    prompt: str
    optional: bool = False
    fields: list[dict[str, Any]] = Field(default_factory=list)


class WizardView(BaseModel):
    preset_name: str
    preset_description: str
    documentation_url: str | None = None
    steps: list[WizardStepView] = Field(default_factory=list)


class WizardStepRequest(BaseModel):
    step_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class WizardStepResponse(BaseModel):
    ok: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    next_step: str | None = None


@router.get("/{name}/wizard", response_model=WizardView)
def get_preset_wizard_view(name: str) -> WizardView:
    if name not in list_preset_names():
        raise HTTPException(status_code=404, detail=f"unknown preset: {name}")
    wizard = get_preset_wizard(name)
    if wizard is None:
        raise HTTPException(status_code=404, detail="no wizard registered")
    raw = wizard.to_dict()
    return WizardView(
        preset_name=raw["preset_name"],
        preset_description=raw["preset_description"],
        documentation_url=raw.get("documentation_url"),
        steps=[WizardStepView(**s) for s in raw["steps"]],
    )


@router.post("/{name}/wizard/step", response_model=WizardStepResponse)
def run_preset_wizard_step(
    name: str,
    body: WizardStepRequest,
    ctx: RequestContext = Depends(current_context),
) -> WizardStepResponse:
    if name not in list_preset_names():
        raise HTTPException(status_code=404, detail=f"unknown preset: {name}")
    wizard = get_preset_wizard(name)
    if wizard is None:
        raise HTTPException(status_code=404, detail="no wizard registered")
    step = wizard.step(body.step_id)
    if step is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown step {body.step_id!r}; valid steps: {[s.id for s in wizard.steps]}",
        )
    payload = dict(body.payload)
    payload.setdefault("workspace_id", ctx.workspace_id)
    payload.setdefault("project_id", ctx.project_id)
    payload.setdefault("owner_user_id", ctx.user_id)
    payload.setdefault("created_by", ctx.user_id)
    result = wizard.run_step(body.step_id, payload)
    if result.next_step is None:
        ids = [s.id for s in wizard.steps]
        try:
            idx = ids.index(body.step_id)
            next_id = ids[idx + 1] if idx + 1 < len(ids) else None
        except ValueError:
            next_id = None
    else:
        next_id = result.next_step
    return WizardStepResponse(
        ok=result.ok,
        message=result.message,
        details=result.details,
        next_step=next_id,
    )


@router.get("/{name}/configs")
def list_preset_configs(
    name: str,
    ctx: RequestContext = Depends(current_context),
) -> list[dict[str, Any]]:
    """Return the project-scoped DatasetPipelineConfigRows tied to this preset."""
    if name not in list_preset_names():
        raise HTTPException(status_code=404, detail=f"unknown preset: {name}")
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_data_control import DatasetPipelineConfigRow
    except Exception:  # pragma: no cover
        return []
    rows: list[dict[str, Any]] = []
    with get_session() as session:
        query = session.query(DatasetPipelineConfigRow)
        if ctx.project_id:
            query = query.filter(DatasetPipelineConfigRow.project_id == ctx.project_id)
        for row in query.all():
            cfg = dict(row.config_json or {})
            if str(cfg.get("preset")) != name:
                continue
            rows.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "version": int(row.version or 1),
                    "status": row.status,
                    "tags": list(row.tags or []),
                    "sinks": list(row.sinks or []),
                    "automations": list(row.automations or []),
                    "is_active": bool(row.is_active),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
    return rows


__all__ = ["router"]
