"""Data Browser → pipeline export endpoints + generic ingestion entrypoints.

Surfaces:

- ``POST /data/preview/stream`` — wrap the existing ``/live/subscribe``
  with a curated indicator/transform overlay so the Data Browser can
  open a live preview WebSocket without users having to spell out the
  full venue payload.
- ``POST /pipelines/from-browser`` — spool a Data Browser selection
  (securities + indicator specs + transformations) into a feature-set
  spec via the existing feature-sets API so it can be materialized by
  the Celery worker downstream.
- ``POST /pipelines/ingest`` — kick off a generic file/folder/ZIP
  ingestion into the Iceberg catalog.
- ``GET  /pipelines/discovery/preview`` — synchronous discovery preview
  (no extraction) used by the wizard.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted
from aqp.config import settings
from aqp.data.loading_templates import (
    LoadingTemplate,
    build_template_payload,
    get_loading_template,
    list_loading_templates,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["data-pipelines"])


class StreamPreviewRequest(BaseModel):
    venue: str = Field(default="simulated", description="alpaca | ibkr | kafka | simulated")
    symbols: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)
    poll_cadence_seconds: float = Field(default=5.0, ge=1.0, le=60.0)


@router.post("/data/preview/stream")
async def preview_stream(req: StreamPreviewRequest) -> dict[str, Any]:
    """Open a live subscription enriched with indicator/transform context.

    The actual computation of indicators/transforms over the streaming
    feed lives in the Flink jobs (``features.indicators.v1`` topic). Here
    we simply forward the subscription, return the WS URL, and echo the
    user's requested overlays so the browser can render them client-side.
    """
    if not req.symbols:
        raise HTTPException(400, "symbols must not be empty")

    # Reuse the live router via in-process HTTP to avoid duplicating
    # SubscribeRequest validation and websocket plumbing.
    base = settings.api_url.rstrip("/")
    payload = {
        "venue": req.venue,
        "symbols": req.symbols,
        "poll_cadence_seconds": req.poll_cadence_seconds,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{base}/live/subscribe", json=payload)
            resp.raise_for_status()
            sub = resp.json()
    except httpx.HTTPError as exc:  # pragma: no cover - exercised in integration
        raise HTTPException(502, f"live/subscribe failed: {exc}") from exc

    return {
        "channel_id": sub.get("channel_id"),
        "ws_url": sub.get("ws_url"),
        "symbols": req.symbols,
        "indicators": req.indicators,
        "transformations": req.transformations,
    }


class PipelineExportRequest(BaseModel):
    name: str = Field(..., description="Feature set name (kebab/snake_case)")
    description: str = Field(default="Generated from Data Browser export")
    symbols: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    fundamentals: list[str] = Field(default_factory=list)
    transformations: list[str] = Field(default_factory=list)
    default_lookback_days: int = Field(default=60, ge=1, le=3000)


@router.post("/pipelines/from-browser")
def export_pipeline(req: PipelineExportRequest) -> dict[str, Any]:
    """Materialize a feature-set spec from a Data Browser selection.

    Flat pipeline:

    1. Compose the user's indicator/fundamental/transformation picks
       into IndicatorZoo spec strings.
    2. Insert into the ``feature_sets`` table via the existing model
       (best-effort persistence — when SQL is unavailable we still
       return the compiled spec so the UI shows what it would have
       inserted).
    3. Hand a Kafka topic id back so downstream Flink jobs and the
       live dashboard can subscribe.
    """
    specs: list[str] = []
    specs.extend(req.indicators)
    for fund in req.fundamentals:
        specs.append(f"Field:{fund}")
    for tx in req.transformations:
        specs.append(tx)

    feature_set_id: str | None = None
    persisted = False
    error: str | None = None
    try:  # pragma: no cover - DB-dependent path
        import datetime as _dt

        from aqp.persistence.db import get_session
        from aqp.persistence.models import FeatureSet

        description = (
            f"{req.description}\n\n"
            f"symbols: {', '.join(req.symbols)}\n"
            f"sources: {', '.join(req.sources)}\n"
            f"indicators: {', '.join(req.indicators)}\n"
            f"fundamentals: {', '.join(req.fundamentals)}\n"
            f"transformations: {', '.join(req.transformations)}"
        )
        with get_session() as session:
            entry = FeatureSet(
                name=req.name,
                description=description,
                kind="composite",
                specs=specs,
                tags=["data-browser-export"],
                default_lookback_days=req.default_lookback_days,
                created_at=_dt.datetime.utcnow(),
                updated_at=_dt.datetime.utcnow(),
            )
            session.add(entry)
            session.flush()
            feature_set_id = entry.id
            persisted = True
    except Exception as exc:  # noqa: BLE001
        error = str(exc)

    topic = f"features.preview.{req.name.replace(' ', '_').lower()}.v1"
    return {
        "feature_set_id": feature_set_id,
        "feature_set_name": req.name,
        "specs": specs,
        "topic": topic,
        "persisted": persisted,
        "error": error,
        "preview_id": uuid.uuid4().hex[:12],
    }


# ---------------------------------------------------------------------------
# Generic ingestion (file / folder / ZIP → Iceberg)
# ---------------------------------------------------------------------------


class IngestPathRequest(BaseModel):
    path: str = Field(..., description="Absolute path on the host filesystem")
    namespace: str | None = Field(default=None, description="Iceberg namespace; defaults to AQP_ICEBERG_NAMESPACE_DEFAULT")
    table_prefix: str | None = Field(default=None, description="Optional prefix prepended to derived table names")
    annotate: bool = Field(default=True, description="Run the LLM annotation step after materialization")
    max_rows_per_dataset: int | None = Field(default=None, ge=1)
    max_files_per_dataset: int | None = Field(default=None, ge=1)


class AlphaVantageHistoryIngestRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    function: str = Field(default="daily_adjusted", description="intraday | daily | daily_adjusted | weekly | monthly")
    interval: str | None = Field(default=None, description="1min | 5min | 15min | 30min | 60min for intraday")
    outputsize: str = Field(default="full", description="compact | full")
    month: str | None = Field(default=None, description="YYYY-MM for intraday history")
    adjusted: bool | None = None
    extended_hours: bool | None = None
    entitlement: str | None = None
    namespace: str = Field(default="aqp_alpha_vantage")
    table: str = Field(default="stock_history")
    cache: bool = True
    cache_ttl: float | None = Field(default=None, ge=0)
    extra_params: dict[str, Any] = Field(default_factory=dict)


@router.post("/pipelines/ingest", response_model=TaskAccepted)
def ingest_path(req: IngestPathRequest) -> TaskAccepted:
    p = Path(req.path).expanduser()
    if not p.exists():
        raise HTTPException(400, f"path does not exist: {p}")

    from aqp.tasks.ingestion_tasks import ingest_local_path

    async_result = ingest_local_path.delay(
        str(p),
        req.namespace,
        req.table_prefix,
        bool(req.annotate),
        req.max_rows_per_dataset,
        req.max_files_per_dataset,
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/pipelines/alpha-vantage/history", response_model=TaskAccepted)
def ingest_alpha_vantage_history(req: AlphaVantageHistoryIngestRequest) -> TaskAccepted:
    if not req.symbols:
        raise HTTPException(400, "symbols must not be empty")
    from aqp.tasks.ingestion_tasks import ingest_alpha_vantage_history as task

    async_result = task.delay(req.model_dump())
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


class AlphaVantageEndpointBulkRequest(BaseModel):
    endpoints: list[str] = Field(default_factory=list, description="Function ids from /alpha-vantage/functions")
    symbols: list[str] | str = Field(default="all_active", description="Explicit symbol list, or 'all_active'")
    filters: dict[str, Any] = Field(default_factory=dict, description="Optional active-universe filters (exchange, asset_class, security_type)")
    limit: int | None = Field(default=None, ge=1, description="Optional cap when symbols='all_active'")
    cache: bool = Field(default=True)
    cache_ttl: float | None = Field(default=None, ge=0)


class AlphaVantageIntradayPlanRequest(BaseModel):
    symbols: list[str] | str = Field(default="all_active")
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int | None = Field(default=None, ge=1)
    interval: str = Field(default="1min")
    lookback_months: int = Field(default=36, ge=1)
    manifest_dir: str | None = None
    entitlement: str | None = None


class AlphaVantageIntradayLoadRequest(BaseModel):
    manifest_path: str
    batch_size: int | None = Field(default=None, ge=1)
    repair: bool = False
    cache: bool = True
    cache_ttl: float | None = Field(default=None, ge=0)


class AlphaVantageIntradayDeltaLoadOptions(BaseModel):
    batch_size: int | None = Field(default=None, ge=1)
    repair: bool = False
    cache: bool = True
    cache_ttl: float | None = Field(default=None, ge=0)


class AlphaVantageIntradayDeltaRequest(BaseModel):
    plan: AlphaVantageIntradayPlanRequest = Field(default_factory=AlphaVantageIntradayPlanRequest)
    load: AlphaVantageIntradayDeltaLoadOptions | None = None


class LoadingTemplateRunRequest(BaseModel):
    overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Deep-merged onto the template default payload before dispatch.",
    )
    dry_run: bool = Field(
        default=False,
        description="Return the resolved payload without queuing a Celery task.",
    )


@router.get("/pipelines/templates", response_model=list[LoadingTemplate])
def loading_templates() -> list[LoadingTemplate]:
    """List curated loading templates for the visual data workflow editor."""
    return list_loading_templates()


@router.get("/pipelines/templates/{template_id}", response_model=LoadingTemplate)
def loading_template(template_id: str) -> LoadingTemplate:
    try:
        return get_loading_template(template_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown loading template: {template_id}") from exc


@router.post("/pipelines/templates/{template_id}/run")
def run_loading_template(template_id: str, req: LoadingTemplateRunRequest) -> dict[str, Any]:
    """Resolve and queue a loading template.

    Templates are intentionally thin routing metadata over the existing
    Celery-backed ingestion tasks, so progress continues to stream through
    the normal ``/chat/stream/{task_id}`` channel.
    """
    try:
        template, payload = build_template_payload(template_id, req.overrides)
    except KeyError as exc:
        raise HTTPException(404, f"unknown loading template: {template_id}") from exc

    if req.dry_run:
        return {
            "template_id": template.id,
            "endpoint": template.endpoint,
            "run_kind": template.run_kind,
            "dry_run": True,
            "payload": payload,
        }

    if template.run_kind == "alpha_vantage_intraday_delta":
        from aqp.tasks.ingestion_tasks import run_alpha_vantage_intraday_delta

        async_result = run_alpha_vantage_intraday_delta.delay(payload)
    elif template.run_kind == "alpha_vantage_endpoints":
        endpoints = payload.get("endpoints") or []
        if not endpoints:
            raise HTTPException(400, "at least one endpoint id is required")
        from aqp.tasks.ingestion_tasks import load_alpha_vantage_endpoints

        async_result = load_alpha_vantage_endpoints.delay(payload)
    elif template.run_kind == "ingest_local_path":
        path = str(payload.get("path") or "").strip()
        if not path:
            raise HTTPException(400, "path is required")
        p = Path(path).expanduser()
        if not p.exists():
            raise HTTPException(400, f"path does not exist: {p}")
        from aqp.tasks.ingestion_tasks import ingest_local_path

        async_result = ingest_local_path.delay(
            str(p),
            payload.get("namespace"),
            payload.get("table_prefix"),
            bool(payload.get("annotate", True)),
            payload.get("max_rows_per_dataset"),
            payload.get("max_files_per_dataset"),
        )
    else:  # pragma: no cover - protects future template additions
        raise HTTPException(500, f"unsupported loading template run kind: {template.run_kind}")

    return {
        "template_id": template.id,
        "endpoint": template.endpoint,
        "run_kind": template.run_kind,
        "task_id": async_result.id,
        "stream_url": f"/chat/stream/{async_result.id}",
    }


@router.post("/pipelines/alpha-vantage/endpoints", response_model=TaskAccepted)
def queue_alpha_vantage_endpoints(req: AlphaVantageEndpointBulkRequest) -> TaskAccepted:
    if not req.endpoints:
        raise HTTPException(400, "at least one endpoint id is required")
    from aqp.tasks.ingestion_tasks import load_alpha_vantage_endpoints

    async_result = load_alpha_vantage_endpoints.delay(req.model_dump())
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/pipelines/alpha-vantage/intraday/plan", response_model=TaskAccepted)
def queue_alpha_vantage_intraday_plan(req: AlphaVantageIntradayPlanRequest) -> TaskAccepted:
    from aqp.tasks.ingestion_tasks import plan_alpha_vantage_intraday

    async_result = plan_alpha_vantage_intraday.delay(req.model_dump())
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/pipelines/alpha-vantage/intraday/load", response_model=TaskAccepted)
def queue_alpha_vantage_intraday_load(req: AlphaVantageIntradayLoadRequest) -> TaskAccepted:
    from aqp.tasks.ingestion_tasks import load_alpha_vantage_intraday_components

    async_result = load_alpha_vantage_intraday_components.delay(req.model_dump())
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/pipelines/alpha-vantage/intraday/delta", response_model=TaskAccepted)
def queue_alpha_vantage_intraday_delta(req: AlphaVantageIntradayDeltaRequest) -> TaskAccepted:
    from aqp.tasks.ingestion_tasks import run_alpha_vantage_intraday_delta

    payload = {
        "plan": req.plan.model_dump(),
        "load": req.load.model_dump() if req.load else {},
    }
    async_result = run_alpha_vantage_intraday_delta.delay(payload)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/pipelines/discovery/preview")
def discovery_preview(path: str) -> dict[str, Any]:
    """Run a read-only discovery walk and return the candidate datasets."""
    p = Path(path).expanduser()
    if not p.exists():
        raise HTTPException(400, f"path does not exist: {p}")
    try:
        from aqp.data.pipelines import discover_datasets

        datasets = discover_datasets(p)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"discovery failed: {exc}") from exc
    return {
        "source_path": str(p),
        "datasets": [d.to_dict() for d in datasets if d.family != "__assets__"],
        "extras": [
            entry
            for d in datasets
            if d.family == "__assets__"
            for entry in d.inventory_extra
        ],
    }


# ---------------------------------------------------------------------------
# Director: read-only plan preview + batch regulatory ingest
# ---------------------------------------------------------------------------


_REGULATORY_NAMESPACES = {
    "cfpb": "aqp_cfpb",
    "uspto": "aqp_uspto",
    "fda": "aqp_fda",
    "sec": "aqp_sec",
}


@router.get("/pipelines/director/plan")
def director_plan_preview(
    path: str,
    namespace: str | None = None,
    director_enabled: bool = True,
) -> dict[str, Any]:
    """Run discovery + Director planning *without* materialising anything.

    Useful for the Data Browser UI: the user sees how Nemotron will
    consolidate / split / rename the dataset families before kicking
    off an ingest.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise HTTPException(400, f"path does not exist: {p}")
    try:
        from aqp.data.pipelines import (
            discover_datasets,
            plan_ingestion,
        )
        from aqp.data.pipelines.director import _identity_plan  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"pipelines unavailable: {exc}") from exc

    try:
        datasets = discover_datasets(p)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"discovery failed: {exc}") from exc

    ns = (namespace or settings.iceberg_namespace_default or "aqp").strip() or "aqp"
    if not director_enabled:
        plan = _identity_plan(datasets, source_path=str(p), namespace=ns)
    else:
        try:
            plan = plan_ingestion(
                datasets,
                source_path=str(p),
                namespace=ns,
                allowed_namespaces=[ns],
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"director planning failed: {exc}") from exc

    return {
        "source_path": str(p),
        "namespace": ns,
        "datasets_discovered": sum(1 for d in datasets if d.family != "__assets__"),
        "plan": plan.to_dict(),
    }


class RegulatoryIngestRequest(BaseModel):
    sources: list[str] = Field(
        default_factory=lambda: ["cfpb", "uspto", "fda", "sec"],
        description="Subset of {cfpb, uspto, fda, sec} to ingest.",
    )
    host_root: str = Field(
        default="/host-downloads",
        description="Container path under which the per-source subdirectories live.",
    )
    annotate: bool = Field(default=True)
    max_rows_per_dataset: int | None = Field(default=None, ge=1)
    max_files_per_dataset: int | None = Field(default=None, ge=1)
    director_enabled: bool = Field(default=True)


@router.post("/pipelines/ingest/regulatory", response_model=TaskAccepted)
def ingest_regulatory(req: RegulatoryIngestRequest) -> TaskAccepted:
    """Dispatch the four regulatory corpora to the Director-driven pipeline.

    The Celery task runs each source serially in one worker so progress
    streams cleanly through ``/chat/stream/{task_id}``. Per-source
    namespace mapping is fixed at:
    ``cfpb→aqp_cfpb``, ``uspto→aqp_uspto``, ``fda→aqp_fda``,
    ``sec→aqp_sec``.
    """
    sources = [s.strip().lower() for s in req.sources if s.strip()]
    unknown = [s for s in sources if s not in _REGULATORY_NAMESPACES]
    if unknown:
        raise HTTPException(400, f"unknown regulatory sources: {unknown}")

    root = Path(req.host_root).expanduser()
    if not root.exists():
        raise HTTPException(400, f"host_root does not exist: {root}")

    paths: list[str] = []
    namespace_per_path: dict[str, str] = {}
    missing: list[str] = []
    for src in sources:
        candidate = root / src
        if not candidate.exists():
            missing.append(str(candidate))
            continue
        paths.append(str(candidate))
        namespace_per_path[str(candidate)] = _REGULATORY_NAMESPACES[src]

    if missing and not paths:
        raise HTTPException(400, f"no regulatory subdirs present under {root}: {missing}")

    from aqp.tasks.ingestion_tasks import ingest_local_paths_with_director

    async_result = ingest_local_paths_with_director.delay(
        paths,
        namespace_per_path,
        annotate=bool(req.annotate),
        max_rows_per_dataset=req.max_rows_per_dataset,
        max_files_per_dataset=req.max_files_per_dataset,
        director_enabled=bool(req.director_enabled),
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )
