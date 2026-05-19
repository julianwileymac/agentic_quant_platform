"""``/analysis/*`` REST surface for the analysis umbrella.

Routes:

- ``GET    /analysis/flows`` — list flows + JSON-schema-derived param forms.
- ``GET    /analysis/flows/{flow}`` — single flow detail.
- ``POST   /analysis/flows/{flow}/preview`` — sync preview against an inline payload.
- ``POST   /analysis/flows/{flow}/preview-task`` — async preview via Celery.
- ``GET    /analysis/specs`` — list saved specs.
- ``POST   /analysis/specs`` — persist a new spec (idempotent on hash).
- ``GET    /analysis/specs/{slug}`` — current spec + version history.
- ``POST   /analysis/specs/{slug}/run`` — kick :class:`AnalysisRuntime.run`.
- ``GET    /analysis/runs`` — paged ledger of runs.
- ``GET    /analysis/runs/{id}`` — run detail (joined with step results).
- ``GET    /analysis/runs/{id}/results/{step}`` — DuckDB-driven preview
  of one step's gold-tier Iceberg output.
- ``GET    /analysis/datasets/columns`` — convenience proxy for the lab
  forms (``identifier=ns.name``).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.security import secure_router
from aqp.analysis.registry import (
    list_analysis_flows,
    persist_spec,
    resolve_flow,
)
from aqp.analysis.runtime import AnalysisRuntime
from aqp.analysis.spec import AnalysisSpec
from aqp.api.schemas import TaskAccepted

logger = logging.getLogger(__name__)
router = secure_router(prefix="/analysis", tags=["analysis"], default_scope="data:read")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FlowSchemaOut(BaseModel):
    name: str
    namespace: str
    label: str
    description: str
    tags: list[str] = Field(default_factory=list)
    params_schema: dict[str, Any] = Field(default_factory=dict)
    requires_dataset: bool = True
    output_kind: str = "table"
    optional_dependencies: list[str] = Field(default_factory=list)


class PreviewRequest(BaseModel):
    """Input shape for sync + async previews.

    Either ``dataset_cfg`` (built via :func:`aqp.core.registry.build_from_config`)
    or ``iceberg_identifier`` (read via :func:`aqp.data.iceberg_catalog.read_arrow`)
    is acceptable. ``dataset_cfg`` wins when both are supplied.
    """

    params: dict[str, Any] = Field(default_factory=dict)
    dataset_cfg: dict[str, Any] | None = None
    iceberg_identifier: str | None = None
    columns: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=5000, ge=1, le=200_000)


class PreviewResponse(BaseModel):
    flow: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    chart: dict[str, Any] | None = None
    error: str | None = None
    iceberg_identifier: str | None = None


class SpecCreateRequest(BaseModel):
    spec: dict[str, Any]


class SpecRunRequest(BaseModel):
    target: str = Field(default="run", pattern="^(run|preview)$")


class SpecSummary(BaseModel):
    id: str
    name: str
    slug: str
    kind: str
    description: str | None = None
    current_version: int = 1
    status: str = "draft"
    annotations: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SpecVersionSummary(BaseModel):
    id: str
    version: int
    spec_hash: str
    created_at: datetime
    notes: str | None = None


class SpecDetail(SpecSummary):
    payload: dict[str, Any] = Field(default_factory=dict)
    versions: list[SpecVersionSummary] = Field(default_factory=list)


class RunSummary(BaseModel):
    id: str
    spec_id: str | None = None
    version_id: str | None = None
    target: str
    task_id: str | None = None
    status: str
    dataset_descriptor: str | None = None
    iceberg_result_table: str | None = None
    error: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)


class StepResultSummary(BaseModel):
    id: str
    step_alias: str
    flow: str
    status: str
    params_json: dict[str, Any] = Field(default_factory=dict)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    artifact_uri: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    created_at: datetime


class RunDetail(RunSummary):
    steps: list[StepResultSummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Flow catalog
# ---------------------------------------------------------------------------


@router.get("/flows", response_model=list[FlowSchemaOut])
def list_flows(namespace: str | None = None) -> list[FlowSchemaOut]:
    schemas = list_analysis_flows()
    if namespace:
        schemas = [s for s in schemas if s.namespace == namespace]
    return [FlowSchemaOut(**s.model_dump()) for s in schemas]


@router.get("/flows/{flow}", response_model=FlowSchemaOut)
def get_flow(flow: str) -> FlowSchemaOut:
    try:
        descriptor = resolve_flow(flow)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FlowSchemaOut(**descriptor.schema().model_dump())


# ---------------------------------------------------------------------------
# Preview (sync + async)
# ---------------------------------------------------------------------------


def _resolve_dataset(req: PreviewRequest) -> Any:
    if req.dataset_cfg:
        from aqp.core.registry import build_from_config

        handler = build_from_config(req.dataset_cfg)
        df = handler.fetch() if hasattr(handler, "fetch") else handler
        return df
    if req.iceberg_identifier:
        from aqp.data import iceberg_catalog

        cols = list(req.columns) or None
        limit = int(req.limit) if req.limit else None
        arrow_table = iceberg_catalog.read_arrow(
            req.iceberg_identifier, columns=cols, limit=limit
        )
        if arrow_table is None:
            raise HTTPException(
                404, f"Iceberg table {req.iceberg_identifier!r} not found"
            )
        return arrow_table.to_pandas()
    return None


@router.post("/flows/{flow}/preview", response_model=PreviewResponse)
def preview_flow(flow: str, req: PreviewRequest) -> PreviewResponse:
    try:
        resolve_flow(flow)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    try:
        df = _resolve_dataset(req)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"dataset resolution failed: {exc}") from exc
    runtime = AnalysisRuntime()
    try:
        result = runtime.preview(flow, df, req.params)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return PreviewResponse(
        flow=flow,
        metrics=result.metrics,
        rows=list(result.rows or []),
        artifacts=dict(result.artifacts or {}),
        chart=result.chart,
        error=result.error,
        iceberg_identifier=result.iceberg_identifier,
    )


@router.post("/flows/{flow}/preview-task", response_model=TaskAccepted)
def preview_flow_task(flow: str, req: PreviewRequest) -> TaskAccepted:
    try:
        resolve_flow(flow)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    from aqp.tasks.analysis_flow_tasks import preview_analysis_flow

    payload = {
        "params": req.params,
        "dataset_cfg": req.dataset_cfg,
        "iceberg_identifier": req.iceberg_identifier,
        "columns": req.columns,
        "limit": req.limit,
    }
    async_result = preview_analysis_flow.delay(flow, payload)
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------


def _spec_summary_from_row(row: Any) -> SpecSummary:
    return SpecSummary(
        id=row.id,
        name=row.name,
        slug=row.slug,
        kind=row.kind,
        description=row.description,
        current_version=row.current_version,
        status=row.status,
        annotations=list(row.annotations or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/specs", response_model=list[SpecSummary])
def list_specs(limit: int = Query(default=100, ge=1, le=500)) -> list[SpecSummary]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_analysis import AnalysisSpec as SpecRow

    with get_session() as session:
        rows = (
            session.execute(
                select(SpecRow).order_by(desc(SpecRow.updated_at)).limit(int(limit))
            )
            .scalars()
            .all()
        )
        return [_spec_summary_from_row(r) for r in rows]


@router.post("/specs", response_model=SpecSummary, status_code=201)
def create_or_update_spec(req: SpecCreateRequest) -> SpecSummary:
    try:
        spec = AnalysisSpec.model_validate(req.spec)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"invalid AnalysisSpec: {exc}") from exc
    persist_spec(spec)
    from aqp.persistence.db import get_session
    from aqp.persistence.models_analysis import AnalysisSpec as SpecRow

    with get_session() as session:
        row = (
            session.execute(select(SpecRow).where(SpecRow.slug == spec.slug))
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(500, "persist_spec did not produce a row")
        return _spec_summary_from_row(row)


@router.get("/specs/{slug}", response_model=SpecDetail)
def get_spec(slug: str) -> SpecDetail:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_analysis import (
        AnalysisSpec as SpecRow,
        AnalysisSpecVersion,
    )

    with get_session() as session:
        row = (
            session.execute(select(SpecRow).where(SpecRow.slug == slug))
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, f"analysis spec {slug!r} not found")
        versions = (
            session.execute(
                select(AnalysisSpecVersion)
                .where(AnalysisSpecVersion.spec_id == row.id)
                .order_by(desc(AnalysisSpecVersion.version))
            )
            .scalars()
            .all()
        )
        latest_payload: dict[str, Any] = {}
        if versions:
            latest_payload = versions[0].payload or {}
        return SpecDetail(
            **_spec_summary_from_row(row).model_dump(),
            payload=latest_payload,
            versions=[
                SpecVersionSummary(
                    id=v.id,
                    version=v.version,
                    spec_hash=v.spec_hash,
                    created_at=v.created_at,
                    notes=v.notes,
                )
                for v in versions
            ],
        )


@router.post("/specs/{slug}/run", response_model=TaskAccepted)
def run_spec(slug: str, req: SpecRunRequest | None = None) -> TaskAccepted:
    """Kick :meth:`AnalysisRuntime.run` for a registered spec on Celery."""
    from aqp.tasks.analysis_flow_tasks import run_analysis_spec

    target = (req.target if req else "run") or "run"
    async_result = run_analysis_spec.delay(slug, None, target=target)
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def _run_summary_from_row(row: Any) -> RunSummary:
    return RunSummary(
        id=row.id,
        spec_id=row.spec_id,
        version_id=row.version_id,
        target=row.target,
        task_id=row.task_id,
        status=row.status,
        dataset_descriptor=row.dataset_descriptor,
        iceberg_result_table=row.iceberg_result_table,
        error=row.error,
        started_at=row.started_at,
        ended_at=row.ended_at,
        result_summary=row.result_summary or {},
    )


@router.get("/runs", response_model=list[RunSummary])
def list_runs(
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = None,
    spec_id: str | None = None,
) -> list[RunSummary]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_analysis import AnalysisRun

    with get_session() as session:
        stmt = select(AnalysisRun).order_by(desc(AnalysisRun.started_at)).limit(int(limit))
        if status:
            stmt = stmt.where(AnalysisRun.status == status)
        if spec_id:
            stmt = stmt.where(AnalysisRun.spec_id == spec_id)
        rows = session.execute(stmt).scalars().all()
        return [_run_summary_from_row(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str) -> RunDetail:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_analysis import AnalysisRun, AnalysisStepResult

    with get_session() as session:
        row = session.get(AnalysisRun, run_id)
        if row is None:
            raise HTTPException(404, f"analysis run {run_id!r} not found")
        steps = (
            session.execute(
                select(AnalysisStepResult)
                .where(AnalysisStepResult.run_id == run_id)
                .order_by(AnalysisStepResult.created_at)
            )
            .scalars()
            .all()
        )
        return RunDetail(
            **_run_summary_from_row(row).model_dump(),
            steps=[
                StepResultSummary(
                    id=s.id,
                    step_alias=s.step_alias,
                    flow=s.flow,
                    status=s.status,
                    params_json=dict(s.params_json or {}),
                    metrics_json=dict(s.metrics_json or {}),
                    artifact_uri=s.artifact_uri,
                    duration_ms=s.duration_ms,
                    error=s.error,
                    created_at=s.created_at,
                )
                for s in steps
            ],
        )


@router.get("/runs/{run_id}/results/{step}")
def get_step_results(
    run_id: str,
    step: str,
    limit: int = Query(default=200, ge=1, le=10_000),
) -> dict[str, Any]:
    """Return a small DuckDB-driven preview of one step's Iceberg output.

    Falls back to ``{rows: []}`` when the step has no Iceberg artifact.
    """
    from aqp.persistence.db import get_session
    from aqp.persistence.models_analysis import AnalysisStepResult

    with get_session() as session:
        row = (
            session.execute(
                select(AnalysisStepResult)
                .where(AnalysisStepResult.run_id == run_id)
                .where(AnalysisStepResult.step_alias == step)
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, f"step {step!r} not found in run {run_id!r}")
        if not row.artifact_uri:
            return {
                "step": step,
                "rows": [],
                "metrics": dict(row.metrics_json or {}),
                "artifact_uri": None,
            }
        try:
            from aqp.data import iceberg_catalog

            arrow_table = iceberg_catalog.read_arrow(row.artifact_uri, limit=int(limit))
            if arrow_table is None:
                return {
                    "step": step,
                    "rows": [],
                    "metrics": dict(row.metrics_json or {}),
                    "artifact_uri": row.artifact_uri,
                }
            df = arrow_table.to_pandas()
            return {
                "step": step,
                "rows": df.to_dict(orient="records"),
                "metrics": dict(row.metrics_json or {}),
                "artifact_uri": row.artifact_uri,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Iceberg read failed for %s: %s", row.artifact_uri, exc, exc_info=True
            )
            raise HTTPException(500, f"iceberg read failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@router.get("/datasets/columns")
def dataset_columns(identifier: str = Query(...)) -> dict[str, Any]:
    """Return the column list (and dtypes) for an Iceberg identifier.

    Drives the lab's column-autocomplete inputs.
    """
    from aqp.data import iceberg_catalog

    arrow_table = iceberg_catalog.read_arrow(identifier, limit=1)
    if arrow_table is None:
        raise HTTPException(404, f"Iceberg table {identifier!r} not found")
    columns = [
        {"name": field.name, "dtype": str(field.type)}
        for field in arrow_table.schema
    ]
    return {"identifier": identifier, "columns": columns}
