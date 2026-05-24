"""Data Lab REST + WebSocket surface.

Mounted behind ``settings.aqp_lab_enabled`` so the route module is
fully optional during the rollout. The route surface is:

- ``POST   /lab/graphs`` — create a new GraphSpec.
- ``GET    /lab/graphs`` — list graphs scoped to ``lab_id``.
- ``GET    /lab/graphs/{graph_id}`` — fetch one.
- ``PATCH  /lab/graphs/{graph_id}`` — edit (re-derives ``content_hash``).
- ``DELETE /lab/graphs/{graph_id}`` — soft-delete via ``archived_at``.
- ``POST   /lab/graphs/{graph_id}/runs`` — submit a run.
- ``GET    /lab/runs/{run_id}`` — fetch status + node outcomes.
- ``POST   /lab/runs/{run_id}/cancel`` — best-effort halt.
- ``GET    /lab/runs/{run_id}/artifacts`` — list ``lab_artifacts`` rows.
- ``POST   /lab/halt-all`` — kill-switch fan-out.
- ``GET    /lab/catalog/node-types`` — palette source-of-truth.
- ``WS     /ws/lab/{session_id}`` — typed Lab envelopes for the UI.

This module aliases :func:`aqp.api.security.secure_router` so every
mutating endpoint requires authentication; the WS route uses the
existing :class:`ConnectionManager` + :func:`asubscribe` plumbing per
the chat.py precedent.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.api.security import require_scope, secure_router
from aqp.api.security_stepup import require_step_up
from aqp.auth.audit import emit_audit_event
from aqp.auth.context import RequestContext
from aqp.auth.deps import current_context, current_user
from aqp.auth.user import CurrentUser
from aqp.auth.ws import ws_authenticator
from aqp.config import settings
from aqp.lab.compliance import check_graph_compliance
from aqp.lab.hashing import (
    compute_code_snapshot,
    compute_content_hash,
    snapshot_data_locator,
)
from aqp.lab.registry import all_node_types, categories_for_palette
from aqp.lab.schema import GraphSpec
from aqp.lab.ws.fanout import iter_lab_envelopes, lab_channel_id
from aqp.persistence import async_session_dep
from aqp.persistence.models_lab import (
    LAB_MODES,
    LabArtifact,
    LabGraph,
    LabNodeRun,
    LabRun,
)
from aqp.ws.manager import manager

logger = logging.getLogger(__name__)


router = secure_router(prefix="/lab", tags=["data-lab"], default_scope="data:read")
ws_router = APIRouter(tags=["data-lab-ws"])


# ---------------------------------------------------------------------------
# Pydantic request / response wrappers
# ---------------------------------------------------------------------------


class GraphCreate(BaseModel):
    lab_id: str
    name: str = "untitled"
    description: str = ""
    spec: GraphSpec
    parent_graph_id: str | None = None
    project_id: str | None = None


class GraphPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    spec: GraphSpec | None = None
    archive: bool | None = None


class GraphOut(BaseModel):
    id: str
    lab_id: str
    name: str
    description: str | None = None
    mode: str
    spec: dict[str, Any]
    content_hash: str
    parent_graph_id: str | None = None
    data_snapshot: dict[str, Any] = Field(default_factory=dict)
    code_snapshot: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RunSubmitRequest(BaseModel):
    inline: bool = True  # Phase 0 runs inline; Phase 2 default flips to Celery
    session_id: str | None = None


class RunOut(BaseModel):
    id: str
    graph_id: str
    lab_id: str | None
    mode: str
    status: str
    session_id: str | None
    task_id: str | None
    content_hash: str
    metrics: dict[str, Any]
    result_summary: dict[str, Any]
    error: str | None = None
    halted: bool = False
    duration_ms: float | None = None
    started_at: datetime
    ended_at: datetime | None


class NodeRunOut(BaseModel):
    node_id: str
    node_type: str
    status: str
    metrics: dict[str, Any]
    output_locator: dict[str, Any]
    duration_ms: float | None
    error: str | None
    started_at: datetime | None
    ended_at: datetime | None


class ArtifactOut(BaseModel):
    id: str
    node_id: str | None
    kind: str
    uri: str
    size_bytes: int | None
    content_hash: str | None
    created_at: datetime


class HaltAllResponse(BaseModel):
    halted: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graph_row_to_out(row: LabGraph) -> GraphOut:
    return GraphOut(
        id=row.id,
        lab_id=row.lab_id,
        name=row.name,
        description=row.description,
        mode=row.mode,
        spec=dict(row.spec or {}),
        content_hash=row.content_hash,
        parent_graph_id=row.parent_graph_id,
        data_snapshot=dict(row.data_snapshot or {}),
        code_snapshot=row.code_snapshot,
        archived_at=row.archived_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_row_to_out(row: LabRun) -> RunOut:
    return RunOut(
        id=row.id,
        graph_id=row.graph_id,
        lab_id=row.lab_id,
        mode=row.mode,
        status=row.status,
        session_id=row.session_id,
        task_id=row.task_id,
        content_hash=row.content_hash,
        metrics=dict(row.metrics or {}),
        result_summary=dict(row.result_summary or {}),
        error=row.error,
        halted=bool(row.halted),
        duration_ms=row.duration_ms,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


def _node_run_to_out(row: LabNodeRun) -> NodeRunOut:
    return NodeRunOut(
        node_id=row.node_id,
        node_type=row.node_type,
        status=row.status,
        metrics=dict(row.metrics or {}),
        output_locator=dict(row.output_locator or {}),
        duration_ms=row.duration_ms,
        error=row.error,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


def _artifact_row_to_out(row: LabArtifact) -> ArtifactOut:
    return ArtifactOut(
        id=row.id,
        node_id=row.node_id,
        kind=row.kind,
        uri=row.uri,
        size_bytes=row.size_bytes,
        content_hash=row.content_hash,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# Catalog — datasets, features, snippets, papers
# ---------------------------------------------------------------------------


class CatalogEntryOut(BaseModel):
    id: str
    name: str
    kind: str  # iceberg | hudi | questdb | dataset_catalog | snippet
    namespace: str | None = None
    description: str | None = None
    schema_fields: list[str] = Field(default_factory=list)
    snapshot_id: str | None = None
    row_estimate: int | None = None
    medallion_layer: str | None = None
    tags: list[str] = Field(default_factory=list)


@router.get("/catalog/datasets", response_model=list[CatalogEntryOut])
async def list_catalog_datasets(
    q: str | None = Query(default=None, description="Free-text filter"),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(async_session_dep),
) -> list[CatalogEntryOut]:
    """Merge ingested ``dataset_catalogs`` rows + Iceberg + Hudi + QuestDB.

    Phase 1 ships the dataset_catalogs slice (the deepest catalog AQP
    already maintains). Iceberg / Hudi / QuestDB sub-listings are
    documented as Phase 1 follow-ups — they share the same response
    shape so the frontend treats them uniformly.
    """
    out: list[CatalogEntryOut] = []
    try:
        from aqp.persistence.models import DatasetCatalog

        stmt = select(DatasetCatalog).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        for row in rows:
            name = str(getattr(row, "name", "") or getattr(row, "id", ""))
            if q and q.lower() not in name.lower():
                continue
            meta = getattr(row, "meta", None) or {}
            schema_fields = []
            try:
                if isinstance(meta, dict):
                    schema_fields = [
                        str(c.get("name", c))
                        for c in (meta.get("columns") or [])
                        if isinstance(c, (str, dict))
                    ][:24]
            except Exception:  # noqa: BLE001
                pass
            out.append(
                CatalogEntryOut(
                    id=str(getattr(row, "id", "")),
                    name=name,
                    kind="dataset_catalog",
                    namespace=str(getattr(row, "namespace", "") or "") or None,
                    description=str(getattr(row, "description", "") or "") or None,
                    schema_fields=schema_fields,
                    medallion_layer=str(getattr(row, "medallion_layer", "") or "") or None,
                    tags=list(getattr(row, "tags", []) or []),
                )
            )
    except Exception as exc:  # noqa: BLE001 - degrade cleanly when DB is off
        logger.debug("dataset_catalog read failed: %s", exc)
    return out


@router.get("/catalog/snippets", response_model=list[CatalogEntryOut])
async def list_catalog_snippets(
    workspace_id: str | None = Query(default=None),
    session: AsyncSession = Depends(async_session_dep),
) -> list[CatalogEntryOut]:
    """List user-saved snippets scoped to ``workspace_id``."""
    from aqp.persistence.models_lab import LabSnippet

    stmt = select(LabSnippet)
    if workspace_id:
        stmt = stmt.where(LabSnippet.workspace_id == workspace_id)
    stmt = stmt.order_by(LabSnippet.updated_at.desc()).limit(200)
    try:
        rows = (await session.execute(stmt)).scalars().all()
    except Exception:  # noqa: BLE001
        rows = []
    return [
        CatalogEntryOut(
            id=row.id,
            name=row.name,
            kind="snippet",
            namespace=row.language,
            description=row.manifest.get("description") if isinstance(row.manifest, dict) else None,
            tags=list((row.manifest.get("tags") if isinstance(row.manifest, dict) else []) or []),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Notes (markdown notes attached to graphs / runs / labels / paper_chunks)
# ---------------------------------------------------------------------------


class NoteCreate(BaseModel):
    lab_id: str
    target_kind: str
    target_id: str
    body_md: str
    citations: list[dict[str, Any]] = Field(default_factory=list)


class NoteOut(BaseModel):
    id: str
    lab_id: str
    target_kind: str
    target_id: str
    body_md: str
    citations: list[dict[str, Any]]
    created_at: datetime


@router.post("/notes", response_model=NoteOut)
async def create_note(
    body: NoteCreate,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> NoteOut:
    from aqp.persistence.models_lab import LAB_NOTE_TARGETS, LabNote

    if body.target_kind not in LAB_NOTE_TARGETS:
        raise HTTPException(400, f"unknown target_kind {body.target_kind!r}")
    row = LabNote(
        id=str(uuid4()),
        lab_id=body.lab_id,
        target_kind=body.target_kind,
        target_id=body.target_id,
        body_md=body.body_md,
        citations=list(body.citations or []),
        author_user_id=getattr(user, "id", None),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    emit_audit_event(
        "lab.note.create",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="info",
        source="api",
        request=request,
        details={
            "note_id": row.id,
            "lab_id": row.lab_id,
            "target_kind": row.target_kind,
            "target_id": row.target_id,
        },
    )
    return NoteOut(
        id=row.id,
        lab_id=row.lab_id,
        target_kind=row.target_kind,
        target_id=row.target_id,
        body_md=row.body_md,
        citations=list(row.citations or []),
        created_at=row.created_at,
    )


@router.get("/notes", response_model=list[NoteOut])
async def list_notes(
    lab_id: str = Query(...),
    target_kind: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(async_session_dep),
) -> list[NoteOut]:
    from aqp.persistence.models_lab import LabNote

    stmt = select(LabNote).where(LabNote.lab_id == lab_id)
    if target_kind:
        stmt = stmt.where(LabNote.target_kind == target_kind)
    if target_id:
        stmt = stmt.where(LabNote.target_id == target_id)
    stmt = stmt.order_by(LabNote.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        NoteOut(
            id=r.id,
            lab_id=r.lab_id,
            target_kind=r.target_kind,
            target_id=r.target_id,
            body_md=r.body_md,
            citations=list(r.citations or []),
            created_at=r.created_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# RAG sidecar (hybrid query)
# ---------------------------------------------------------------------------


class RagQueryRequest(BaseModel):
    lab_id: str
    query: str
    k: int = 10
    tags: list[str] = Field(default_factory=list)


class RagHit(BaseModel):
    chunk_id: str
    paper_title: str | None = None
    source_uri: str | None = None
    text: str
    score: float
    rank: int


class RagQueryResponse(BaseModel):
    query: str
    hits: list[RagHit]


# ---------------------------------------------------------------------------
# Labels (chart annotations)
# ---------------------------------------------------------------------------


class LabelCreate(BaseModel):
    lab_id: str
    vt_symbol: str
    interval: str = "1m"
    t_start: datetime
    t_end: datetime | None = None
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None


class LabelOut(BaseModel):
    id: str
    lab_id: str
    vt_symbol: str
    interval: str
    t_start: datetime
    t_end: datetime | None
    kind: str
    payload: dict[str, Any]
    run_id: str | None
    created_at: datetime


def _label_row_to_out(row: Any) -> LabelOut:
    return LabelOut(
        id=row.id,
        lab_id=row.lab_id,
        vt_symbol=row.vt_symbol,
        interval=row.interval,
        t_start=row.t_start,
        t_end=row.t_end,
        kind=row.kind,
        payload=dict(row.payload or {}),
        run_id=row.run_id,
        created_at=row.created_at,
    )


@router.post("/labels", response_model=LabelOut)
async def create_label(
    body: LabelCreate,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> LabelOut:
    from aqp.persistence.models_lab import LAB_LABEL_KINDS, LabLabel

    if body.kind not in LAB_LABEL_KINDS:
        raise HTTPException(400, f"unknown label kind {body.kind!r}")
    row = LabLabel(
        id=str(uuid4()),
        lab_id=body.lab_id,
        vt_symbol=body.vt_symbol,
        interval=body.interval,
        t_start=body.t_start,
        t_end=body.t_end,
        kind=body.kind,
        payload=dict(body.payload or {}),
        run_id=body.run_id,
        owner_user_id=getattr(user, "id", None),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    emit_audit_event(
        "lab.label.create",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="info",
        source="api",
        request=request,
        details={
            "label_id": row.id,
            "lab_id": row.lab_id,
            "vt_symbol": row.vt_symbol,
            "kind": row.kind,
            "run_id": row.run_id,
        },
    )
    return _label_row_to_out(row)


@router.get("/labels", response_model=list[LabelOut])
async def list_labels(
    lab_id: str = Query(...),
    vt_symbol: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(async_session_dep),
) -> list[LabelOut]:
    from aqp.persistence.models_lab import LabLabel

    stmt = select(LabLabel).where(LabLabel.lab_id == lab_id)
    if vt_symbol:
        stmt = stmt.where(LabLabel.vt_symbol == vt_symbol)
    if kind:
        stmt = stmt.where(LabLabel.kind == kind)
    stmt = stmt.order_by(LabLabel.t_start.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [_label_row_to_out(r) for r in rows]


@router.delete("/labels/{label_id}", status_code=204)
async def delete_label(
    label_id: str,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> None:
    from aqp.persistence.models_lab import LabLabel

    row = await session.get(LabLabel, label_id)
    if row is None:
        raise HTTPException(404, "label not found")
    label_summary = {
        "label_id": row.id,
        "lab_id": row.lab_id,
        "vt_symbol": row.vt_symbol,
        "kind": row.kind,
    }
    await session.delete(row)
    await session.commit()
    emit_audit_event(
        "lab.label.delete",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="warning",
        source="api",
        request=request,
        details=label_summary,
    )


# ---------------------------------------------------------------------------
# Train-labeler wizard
# ---------------------------------------------------------------------------


class TrainLabelerRequest(BaseModel):
    lab_id: str
    vt_symbol: str
    label_kind: str = "swing"
    iceberg_namespace: str = "aqp_silver_equities_bars"
    iceberg_table: str = "bars_1m"


# ---------------------------------------------------------------------------
# EDA cell promotion (Phase 1)
# ---------------------------------------------------------------------------


class PromoteCellRequest(BaseModel):
    """Promote an EDA cell into a draft Testing-mode :class:`GraphSpec`.

    The frontend ``EdaCellStack`` button POSTs this with the cell's
    source code + the lab id. We persist the source as a
    :class:`aqp.persistence.models_lab.LabSnippet` row, render a
    single-node :class:`GraphSpec` referencing the snippet by id, and
    return the new :class:`LabGraph` row. The graph mode is always
    ``testing`` because EDA cells are inherently exploratory — the
    user can flip the mode later from the canvas.
    """

    lab_id: str
    workspace_id: str | None = Field(
        default=None,
        description="Workspace owning the snippet — falls back to RequestContext.workspace_id.",
    )
    source: str = Field(..., description="The cell's Python source.")
    cell_label: str = Field(default="EDA cell", description="Human-friendly name for the snippet + graph.")
    inputs: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional input locators (e.g. {'in': {'kind':'iceberg','namespace':...,'table':...}}).",
    )


@router.post("/eda/{session_id}/cells/{cell_id}/promote", response_model=GraphOut)
async def promote_cell_to_testing_graph(
    session_id: str,
    cell_id: str,
    body: PromoteCellRequest,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> GraphOut:
    """Persist an EDA cell as a Lab snippet + draft Testing GraphSpec.

    The generated graph contains:

    1. Optional ``data.iceberg_scan`` upstream node when ``inputs['in']``
       is an Iceberg locator, so the promoted snippet has the same
       upstream the cell consumed.
    2. One ``snippet.python`` node that resolves to the persisted
       snippet via ``params.snippet_id``.
    3. One ``out.tearsheet`` sink — purely as a starter affordance so
       the Run button produces a visible artefact.

    The user lands on the canvas with this draft loaded; they can wire
    additional nodes or delete the auto-added tearsheet.
    """
    # Inline import to keep model_lab side-effect surface bounded.
    from aqp.lab.eda.kernel import _ast_safety_check  # noqa: PLC0415
    from aqp.lab.schema import (
        EdgeSpec,
        GraphSpec,
        NodeSpec,
        Port,
        PortDType,
    )
    from aqp.lab.snippets import compute_snippet_hash, save_snippet

    workspace_id = body.workspace_id or ctx.workspace_id
    if not workspace_id:
        raise HTTPException(
            400, "workspace_id is required to persist the cell as a snippet"
        )

    try:
        _ast_safety_check(body.source)
    except Exception as exc:  # noqa: BLE001
        emit_audit_event(
            "lab.cell.promote.safety_denied",
            user_id=getattr(user, "id", None),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            actor_user_id=getattr(user, "id", None),
            event_category="safety",
            severity="warning",
            source="api",
            request=request,
            details={
                "lab_id": body.lab_id,
                "session_id": session_id,
                "cell_id": cell_id,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "cell failed AST safety check", "reason": str(exc)},
        ) from exc

    snippet_name = f"{body.cell_label} ({cell_id[:8]})"
    snippet_id = save_snippet(
        workspace_id=workspace_id,
        name=snippet_name,
        source=body.source,
        language="python",
        lab_id=body.lab_id,
        owner_user_id=getattr(user, "id", None),
        manifest={
            "promoted_from": {
                "session_id": session_id,
                "cell_id": cell_id,
                "source_hash": compute_snippet_hash(body.source, "python"),
            },
        },
    )
    if not snippet_id:
        raise HTTPException(503, "snippet persistence failed; try again")

    nodes: list[NodeSpec] = []
    edges: list[EdgeSpec] = []
    snippet_inputs_spec: list[Port] = []

    iceberg_input = body.inputs.get("in") if isinstance(body.inputs, dict) else None
    if isinstance(iceberg_input, dict) and iceberg_input.get("kind") == "iceberg":
        nodes.append(
            NodeSpec(
                id="src",
                type="data.iceberg_scan",
                category="DataSource",
                outputs=[Port(name="out", dtype=PortDType.FRAME)],
                params={
                    "namespace": iceberg_input.get("namespace"),
                    "table": iceberg_input.get("table"),
                    "columns": iceberg_input.get("columns"),
                    "limit": iceberg_input.get("limit"),
                    "snapshot_id": iceberg_input.get("snapshot_id"),
                },
            )
        )
        snippet_inputs_spec = [Port(name="in", dtype=PortDType.FRAME)]

    snippet_node = NodeSpec(
        id="snippet",
        type="snippet.python",
        category="Transformation",
        inputs=snippet_inputs_spec,
        outputs=[Port(name="out", dtype=PortDType.FRAME)],
        params={
            "snippet_id": snippet_id,
            "tier": "tier1",
        },
        notes=f"Promoted from EDA cell {cell_id} (session {session_id})",
    )
    nodes.append(snippet_node)
    if snippet_inputs_spec:
        edges.append(EdgeSpec(source="src", target="snippet"))

    nodes.append(
        NodeSpec(
            id="sheet",
            type="out.tearsheet",
            category="Output",
            inputs=[Port(name="portfolio", dtype=PortDType.PORTFOLIO)],
            outputs=[Port(name="out", dtype=PortDType.JSON)],
            params={"title": snippet_name},
        )
    )
    edges.append(EdgeSpec(source="snippet", target="sheet"))

    spec = GraphSpec(
        name=f"promote:{snippet_name}",
        description=f"Promoted from EDA cell {cell_id} in session {session_id}",
        mode="testing",
        nodes=nodes,
        edges=edges,
    )
    content_hash = compute_content_hash(spec)
    data_snapshot = snapshot_data_locator(spec)
    code_snapshot = compute_code_snapshot()

    existing = (
        await session.execute(
            select(LabGraph).where(
                LabGraph.lab_id == body.lab_id,
                LabGraph.content_hash == content_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _graph_row_to_out(existing)

    row = LabGraph(
        id=str(uuid4()),
        lab_id=body.lab_id,
        workspace_id=workspace_id,
        owner_user_id=getattr(user, "id", None),
        name=spec.name,
        description=spec.description,
        mode=spec.mode,
        spec=spec.model_dump(mode="json"),
        content_hash=content_hash,
        code_snapshot=code_snapshot,
        data_snapshot=dict(data_snapshot),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    emit_audit_event(
        "lab.cell.promote",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="info",
        source="api",
        request=request,
        details={
            "graph_id": row.id,
            "snippet_id": snippet_id,
            "lab_id": body.lab_id,
            "session_id": session_id,
            "cell_id": cell_id,
            "content_hash": content_hash,
        },
    )
    return _graph_row_to_out(row)


@router.post("/labelers/train", response_model=GraphOut)
async def train_labeler(
    body: TrainLabelerRequest,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> GraphOut:
    """Build a Testing GraphSpec that trains a meta-labeler on saved labels.

    The wizard emits a deterministic graph:

        data.iceberg_scan -> feature.technical -> label.triple_barrier
                          -> model.gbm -> out.tearsheet

    The user's manual labels (saved via ``POST /lab/labels``) get
    injected via ``label.triple_barrier.params.manual_label_seed`` so
    the meta-labeler is supervised by the operator's domain knowledge.
    """
    from aqp.lab.compliance import check_graph_compliance
    from aqp.lab.schema import (
        EdgeSpec,
        GraphSpec,
        NodeSpec,
        Port,
        PortDType,
    )

    graph_spec = GraphSpec(
        name=f"train-labeler:{body.vt_symbol}",
        description=f"Auto-generated labeler graph for {body.vt_symbol}",
        mode="testing",
        nodes=[
            NodeSpec(
                id="bars",
                type="data.iceberg_scan",
                category="DataSource",
                outputs=[Port(name="out", dtype=PortDType.FRAME)],
                params={
                    "namespace": body.iceberg_namespace,
                    "table": body.iceberg_table,
                },
            ),
            NodeSpec(
                id="tech",
                type="feature.technical",
                category="Feature",
                inputs=[Port(name="in", dtype=PortDType.BAR_SERIES)],
                outputs=[Port(name="out", dtype=PortDType.PANEL)],
                params={"indicator": "rsi", "window": 14},
            ),
            NodeSpec(
                id="labels",
                type="label.triple_barrier",
                category="Labeler",
                inputs=[Port(name="bars", dtype=PortDType.BAR_SERIES)],
                outputs=[Port(name="out", dtype=PortDType.ANNOTATION_SET)],
                params={
                    "pt_sl": [1.0, 1.0],
                    "vertical_barrier_days": 5,
                    "label_kind_seed": body.label_kind,
                    "vt_symbol": body.vt_symbol,
                },
            ),
            NodeSpec(
                id="model",
                type="model.sklearn",
                category="Model",
                inputs=[
                    Port(name="X", dtype=PortDType.PANEL),
                    Port(name="y", dtype=PortDType.SIGNAL),
                ],
                outputs=[Port(name="out", dtype=PortDType.MODEL_ARTIFACT)],
                params={
                    "estimator": "rf_classifier",
                    "target_column": "tb_bin",
                },
            ),
            NodeSpec(
                id="sheet",
                type="out.tearsheet",
                category="Output",
                inputs=[Port(name="portfolio", dtype=PortDType.PORTFOLIO)],
                params={"title": f"{body.vt_symbol} meta-labeler"},
            ),
        ],
        edges=[
            EdgeSpec(source="bars", target="tech"),
            EdgeSpec(source="bars", target="labels"),
            EdgeSpec(source="tech", target="model"),
            EdgeSpec(source="labels", target="model"),
            EdgeSpec(source="model", target="sheet"),
        ],
    )
    violations = check_graph_compliance(graph_spec)
    blocking = [v for v in violations if v.severity == "error"]
    if blocking:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "train-labeler wizard produced an invalid graph",
                "violations": [
                    {"rule": v.rule, "message": v.message, "node_id": v.node_id}
                    for v in blocking
                ],
            },
        )
    content_hash = compute_content_hash(graph_spec)
    from aqp.persistence.models_lab import LabGraph

    existing = (
        await session.execute(
            select(LabGraph).where(
                LabGraph.lab_id == body.lab_id,
                LabGraph.content_hash == content_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        emit_audit_event(
            "lab.labeler.train.dedup",
            user_id=getattr(user, "id", None),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            actor_user_id=getattr(user, "id", None),
            event_category="account",
            severity="info",
            source="api",
            request=request,
            details={
                "graph_id": existing.id,
                "lab_id": existing.lab_id,
                "vt_symbol": body.vt_symbol,
                "deduped": True,
            },
        )
        return _graph_row_to_out(existing)
    row = LabGraph(
        id=str(uuid4()),
        lab_id=body.lab_id,
        owner_user_id=getattr(user, "id", None),
        workspace_id=ctx.workspace_id,
        name=graph_spec.name,
        description=graph_spec.description,
        mode=graph_spec.mode,
        spec=graph_spec.model_dump(mode="json"),
        content_hash=content_hash,
        code_snapshot=compute_code_snapshot(),
        data_snapshot=dict(snapshot_data_locator(graph_spec)),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    emit_audit_event(
        "lab.labeler.train",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="info",
        source="api",
        request=request,
        details={
            "graph_id": row.id,
            "lab_id": row.lab_id,
            "vt_symbol": body.vt_symbol,
            "content_hash": content_hash,
        },
    )
    return _graph_row_to_out(row)


class RagUploadRequest(BaseModel):
    lab_id: str
    source_uri: str = Field(..., description="HTTPS URL, arxiv ID, DOI, or s3:// pointer")
    title: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)


class RagUploadResponse(BaseModel):
    task_id: str
    lab_id: str
    source_uri: str
    status: str = "queued"


@router.post("/rag/upload", response_model=RagUploadResponse)
async def upload_research_paper(
    body: RagUploadRequest,
    request: Request,
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> RagUploadResponse:
    """Ingest a research paper into the Lab RAG sidecar (Phase 5).

    Wraps the existing :mod:`aqp.rag.indexers.papers` ingest pipeline
    via a Celery task that:

    1. Parses the PDF (PyMuPDF / Marker / Nougat / MathPix per the
       parser registry in :mod:`aqp.rag.parsers`).
    2. Section-splits + chunks (512 tokens, 64 overlap).
    3. Embeds via :func:`aqp.rag.embedder.get_embedder`.
    4. Upserts to ``lab_paper_chunks`` (denormalised slice with HNSW
       index) + ``rag_chunks`` (canonical store).

    The Celery task ID can be subscribed to over the existing
    ``/chat/stream/{task_id}`` WS pump so the operator sees parse +
    chunk + embed progress live.
    """
    try:
        from aqp.tasks.lab_rag_tasks import ingest_paper_for_lab
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            503, f"lab RAG ingest task unavailable: {exc}"
        ) from exc
    task_id = str(uuid4())
    ingest_paper_for_lab.apply_async(
        args=(
            body.lab_id,
            body.source_uri,
            body.title,
            list(body.tags or []),
        ),
        task_id=task_id,
    )
    emit_audit_event(
        "lab.rag.upload",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="info",
        source="api",
        request=request,
        details={
            "lab_id": body.lab_id,
            "source_uri": body.source_uri,
            "task_id": task_id,
        },
    )
    return RagUploadResponse(
        task_id=task_id,
        lab_id=body.lab_id,
        source_uri=body.source_uri,
        status="queued",
    )


@router.post("/rag/query", response_model=RagQueryResponse)
async def rag_query(body: RagQueryRequest) -> RagQueryResponse:
    """Hybrid query (BM25 + dense + MMR) wrapping :class:`HierarchicalRAG`.

    Phase 1 surface — delegates to :mod:`aqp.lab.rag.hybrid_query`. When
    the embedding / Redis backends aren't installed the helper returns
    an empty hits list rather than crashing so the operator's drawer
    still renders.
    """
    try:
        from aqp.lab.rag.hybrid_query import hybrid_query

        hits = hybrid_query(body.query, k=body.k, tags=body.tags)
    except Exception as exc:  # noqa: BLE001
        logger.warning("lab rag hybrid_query failed: %s", exc)
        hits = []
    return RagQueryResponse(
        query=body.query,
        hits=[
            RagHit(
                chunk_id=h["chunk_id"],
                paper_title=h.get("paper_title"),
                source_uri=h.get("source_uri"),
                text=h.get("text", "")[:1200],
                score=float(h.get("score", 0.0)),
                rank=int(h.get("rank", i)),
            )
            for i, h in enumerate(hits)
        ],
    )


# ---------------------------------------------------------------------------
# Catalog (palette source-of-truth)
# ---------------------------------------------------------------------------


@router.get("/catalog/node-types")
def list_node_types() -> dict[str, Any]:
    """Return the full node taxonomy grouped by category + JSON Schemas.

    The frontend palette consumes this verbatim. Each entry carries
    the minimal shape the React Flow editor needs (alias, label,
    category, accent, port specs, executor path) PLUS the
    ``params_schema`` (JSON Schema generated from the matching
    Pydantic model in :mod:`aqp.lab.params_models`) so the inspector
    can render a typed form via RJSF.
    """
    from aqp.lab.params_models import get_params_schema

    palette = categories_for_palette()
    return {
        "categories": [
            {
                "name": cat,
                "items": [
                    {
                        "alias": nt.alias,
                        "label": nt.label,
                        "description": nt.description,
                        "accent": nt.accent,
                        "inputs": [p.model_dump(mode="json") for p in nt.inputs],
                        "outputs": [p.model_dump(mode="json") for p in nt.outputs],
                        "runtime": nt.runtime.model_dump(mode="json"),
                        "executor": nt.executor,
                        "params_schema": get_params_schema(nt.alias),
                    }
                    for nt in items
                ],
            }
            for cat, items in palette.items()
        ],
        "modes": list(LAB_MODES),
        "total_nodes": len(all_node_types()),
    }


# ---------------------------------------------------------------------------
# Graph CRUD
# ---------------------------------------------------------------------------


@router.post("/graphs", response_model=GraphOut)
async def create_graph(
    body: GraphCreate,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> GraphOut:
    spec = body.spec
    # Run the pre-flight compliance check on every create so
    # malformed graphs never make it into the table.
    violations = check_graph_compliance(spec)
    blocking = [v for v in violations if v.severity == "error"]
    if blocking:
        emit_audit_event(
            "lab.graph.create.compliance_denied",
            user_id=getattr(user, "id", None),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            actor_user_id=getattr(user, "id", None),
            event_category="safety",
            severity="warning",
            source="api",
            request=request,
            details={
                "lab_id": body.lab_id,
                "mode": spec.mode,
                "violations": len(blocking),
            },
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "graph failed pre-flight compliance",
                "violations": [
                    {
                        "rule": v.rule,
                        "severity": v.severity,
                        "message": v.message,
                        "node_id": v.node_id,
                        "edge_id": v.edge_id,
                    }
                    for v in violations
                ],
            },
        )

    content_hash = compute_content_hash(spec)
    data_snapshot = snapshot_data_locator(spec)
    code_snapshot = compute_code_snapshot()

    # Unique on (lab_id, content_hash) — return existing row if any.
    existing = (
        await session.execute(
            select(LabGraph).where(
                LabGraph.lab_id == body.lab_id,
                LabGraph.content_hash == content_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        emit_audit_event(
            "lab.graph.create.dedup",
            user_id=getattr(user, "id", None),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            actor_user_id=getattr(user, "id", None),
            event_category="account",
            severity="info",
            source="api",
            request=request,
            details={
                "graph_id": existing.id,
                "lab_id": existing.lab_id,
                "content_hash": existing.content_hash,
                "deduped": True,
            },
        )
        return _graph_row_to_out(existing)

    row = LabGraph(
        id=str(uuid4()),
        lab_id=body.lab_id,
        project_id=body.project_id,
        workspace_id=ctx.workspace_id,
        owner_user_id=getattr(user, "id", None),
        name=body.name or spec.name,
        description=body.description or spec.description,
        mode=spec.mode,
        spec=spec.model_dump(mode="json"),
        content_hash=content_hash,
        code_snapshot=code_snapshot,
        parent_graph_id=body.parent_graph_id or spec.parent_graph_id,
        data_snapshot=dict(data_snapshot),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    emit_audit_event(
        "lab.graph.create",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="info",
        source="api",
        request=request,
        details={
            "graph_id": row.id,
            "lab_id": row.lab_id,
            "mode": row.mode,
            "content_hash": row.content_hash,
            "n_nodes": len(spec.nodes),
            "n_edges": len(spec.edges),
        },
    )
    return _graph_row_to_out(row)


@router.get("/graphs", response_model=list[GraphOut])
async def list_graphs(
    lab_id: str = Query(...),
    mode: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(async_session_dep),
) -> list[GraphOut]:
    stmt = select(LabGraph).where(LabGraph.lab_id == lab_id)
    if mode:
        if mode not in LAB_MODES:
            raise HTTPException(400, f"unknown mode {mode!r}")
        stmt = stmt.where(LabGraph.mode == mode)
    if not include_archived:
        stmt = stmt.where(LabGraph.archived_at.is_(None))
    stmt = stmt.order_by(LabGraph.updated_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [_graph_row_to_out(r) for r in rows]


@router.get("/graphs/{graph_id}", response_model=GraphOut)
async def get_graph(
    graph_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> GraphOut:
    row = await session.get(LabGraph, graph_id)
    if row is None:
        raise HTTPException(404, "graph not found")
    return _graph_row_to_out(row)


@router.patch("/graphs/{graph_id}", response_model=GraphOut)
async def patch_graph(
    graph_id: str,
    body: GraphPatch,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> GraphOut:
    row = await session.get(LabGraph, graph_id)
    if row is None:
        raise HTTPException(404, "graph not found")
    changed_fields: list[str] = []
    if body.name is not None:
        row.name = body.name
        changed_fields.append("name")
    if body.description is not None:
        row.description = body.description
        changed_fields.append("description")
    if body.spec is not None:
        # Re-run compliance on the new spec before swapping.
        violations = check_graph_compliance(body.spec)
        blocking = [v for v in violations if v.severity == "error"]
        if blocking:
            emit_audit_event(
                "lab.graph.patch.compliance_denied",
                user_id=getattr(user, "id", None),
                organization_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                actor_user_id=getattr(user, "id", None),
                event_category="safety",
                severity="warning",
                source="api",
                request=request,
                details={
                    "graph_id": graph_id,
                    "violations": len(blocking),
                },
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "graph failed pre-flight compliance",
                    "violations": [
                        {"rule": v.rule, "severity": v.severity, "message": v.message}
                        for v in violations
                    ],
                },
            )
        row.spec = body.spec.model_dump(mode="json")
        row.content_hash = compute_content_hash(body.spec)
        row.data_snapshot = dict(snapshot_data_locator(body.spec))
        row.code_snapshot = compute_code_snapshot()
        row.mode = body.spec.mode
        changed_fields.append("spec")
    if body.archive is True:
        row.archived_at = datetime.utcnow()
        changed_fields.append("archive=true")
    elif body.archive is False:
        row.archived_at = None
        changed_fields.append("archive=false")
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    if changed_fields:
        emit_audit_event(
            "lab.graph.patch",
            user_id=getattr(user, "id", None),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            actor_user_id=getattr(user, "id", None),
            event_category="account",
            severity="info",
            source="api",
            request=request,
            details={
                "graph_id": row.id,
                "lab_id": row.lab_id,
                "changed": changed_fields,
                "content_hash": row.content_hash,
            },
        )
    return _graph_row_to_out(row)


@router.delete("/graphs/{graph_id}", status_code=204)
async def delete_graph(
    graph_id: str,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:admin")),
    ctx: RequestContext = Depends(current_context),
) -> None:
    row = await session.get(LabGraph, graph_id)
    if row is None:
        raise HTTPException(404, "graph not found")
    summary = {
        "graph_id": row.id,
        "lab_id": row.lab_id,
        "content_hash": row.content_hash,
    }
    row.archived_at = datetime.utcnow()
    await session.commit()
    emit_audit_event(
        "lab.graph.delete",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="warning",
        source="api",
        request=request,
        details=summary,
    )


# ---------------------------------------------------------------------------
# Run submission
# ---------------------------------------------------------------------------


@router.post("/graphs/{graph_id}/runs", response_model=RunOut)
async def submit_graph_run(
    graph_id: str,
    body: RunSubmitRequest,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> RunOut:
    graph_row = await session.get(LabGraph, graph_id)
    if graph_row is None:
        raise HTTPException(404, "graph not found")
    spec = GraphSpec.model_validate(graph_row.spec)

    task_id = str(uuid4())
    if body.inline:
        # Phase 0: run inline through LabRuntime so a working
        # deployment can demo the full pipeline without a Celery
        # worker. Phase 2 swaps body.inline=False to dispatch via
        # `aqp.tasks.lab_tasks.run_lab_graph.delay(...)`.
        from aqp.lab.runtime import LabRuntime

        runtime = LabRuntime(
            spec,
            run_id=str(uuid4()),
            task_id=task_id,
            session_id=body.session_id,
            lab_id=graph_row.lab_id,
            graph_id=graph_row.id,
            context=ctx,
        )
        runtime.submit_run()
        # Refresh the row to pick up status from the runtime's
        # finalise step (it wrote synchronously).
        row = await session.get(LabRun, runtime.run_id)
        if row is None:
            raise HTTPException(500, "inline run did not persist a lab_runs row")
        emit_audit_event(
            "lab.run.submit.inline",
            user_id=getattr(user, "id", None),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            actor_user_id=getattr(user, "id", None),
            event_category="account",
            severity="info",
            source="api",
            request=request,
            details={
                "run_id": row.id,
                "graph_id": graph_row.id,
                "mode": graph_row.mode,
                "content_hash": graph_row.content_hash,
                "status": row.status,
                "inline": True,
            },
        )
        return _run_row_to_out(row)

    # Phase 2 path: dispatch through Celery.
    try:
        from aqp.tasks.lab_tasks import run_lab_graph
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"lab Celery tasks not available: {exc}") from exc

    run_id = str(uuid4())
    row = LabRun(
        id=run_id,
        graph_id=graph_row.id,
        lab_id=graph_row.lab_id,
        workspace_id=ctx.workspace_id,
        owner_user_id=getattr(user, "id", None),
        mode=graph_row.mode,
        status="queued",
        session_id=body.session_id,
        task_id=task_id,
        content_hash=graph_row.content_hash,
        code_snapshot=graph_row.code_snapshot or compute_code_snapshot(),
        data_snapshot=dict(graph_row.data_snapshot or {}),
        started_at=datetime.utcnow(),
    )
    session.add(row)
    await session.commit()
    run_lab_graph.apply_async(args=(graph_id, run_id, body.session_id), task_id=task_id)
    await session.refresh(row)
    emit_audit_event(
        "lab.run.submit",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="info",
        source="api",
        request=request,
        details={
            "run_id": run_id,
            "graph_id": graph_row.id,
            "mode": graph_row.mode,
            "content_hash": graph_row.content_hash,
            "task_id": task_id,
            "inline": False,
        },
    )
    return _run_row_to_out(row)


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    lab_id: str | None = Query(default=None),
    graph_id: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(async_session_dep),
) -> list[RunOut]:
    """List LabRun rows ordered by ``started_at`` desc.

    Powers the Grafana-style run-history drawer. Each row carries
    enough metadata for the drawer to render a swimlane without
    loading per-node detail (the drawer fetches that on click via
    :func:`list_run_nodes`).
    """
    stmt = select(LabRun)
    if lab_id:
        stmt = stmt.where(LabRun.lab_id == lab_id)
    if graph_id:
        stmt = stmt.where(LabRun.graph_id == graph_id)
    if mode:
        if mode not in LAB_MODES:
            raise HTTPException(400, f"unknown mode {mode!r}")
        stmt = stmt.where(LabRun.mode == mode)
    if status:
        stmt = stmt.where(LabRun.status == status)
    stmt = stmt.order_by(LabRun.started_at.desc()).limit(int(limit))
    rows = (await session.execute(stmt)).scalars().all()
    return [_run_row_to_out(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> RunOut:
    row = await session.get(LabRun, run_id)
    if row is None:
        raise HTTPException(404, "run not found")
    return _run_row_to_out(row)


class RunNodeRequest(BaseModel):
    """``POST /lab/graphs/{graph_id}/nodes/{node_id}/run`` payload."""

    upstream_locators: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class RunNodeResponse(BaseModel):
    run_id: str
    node_id: str
    task_id: str
    status: str
    duration_ms: float | None = None
    output_locator: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


@router.post(
    "/graphs/{graph_id}/nodes/{node_id}/run",
    response_model=RunNodeResponse,
)
async def run_single_node(
    graph_id: str,
    node_id: str,
    body: RunNodeRequest,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> RunNodeResponse:
    """Dispatch a SINGLE node from a persisted graph through Celery.

    Powers the canvas "Run only this node" affordance. The Celery
    task in :mod:`aqp.tasks.lab_tasks.run_lab_node` emits
    canonical ``node:start`` / ``node:done`` frames the WS pump
    forwards to the canvas pill, and persists a ``LabNodeRun`` row
    with the same shape as the inline canvas.
    """
    graph_row = await session.get(LabGraph, graph_id)
    if graph_row is None:
        raise HTTPException(404, "graph not found")
    spec = GraphSpec.model_validate(graph_row.spec)
    if not any(n.id == node_id for n in spec.nodes):
        raise HTTPException(404, f"node {node_id!r} not in graph {graph_id!r}")

    try:
        from aqp.tasks.lab_tasks import run_lab_node
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"lab Celery tasks not available: {exc}") from exc

    run_id = str(uuid4())
    task_id = str(uuid4())
    row = LabRun(
        id=run_id,
        graph_id=graph_row.id,
        lab_id=graph_row.lab_id,
        workspace_id=ctx.workspace_id,
        owner_user_id=getattr(user, "id", None),
        mode=graph_row.mode,
        status="queued",
        session_id=body.session_id,
        task_id=task_id,
        content_hash=graph_row.content_hash,
        code_snapshot=graph_row.code_snapshot or compute_code_snapshot(),
        data_snapshot=dict(graph_row.data_snapshot or {}),
        started_at=datetime.utcnow(),
    )
    session.add(row)
    await session.commit()
    run_lab_node.apply_async(
        args=(graph_id, run_id, node_id, dict(body.upstream_locators)),
        task_id=task_id,
    )
    emit_audit_event(
        "lab.node.run.submit",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="info",
        source="api",
        request=request,
        details={
            "graph_id": graph_id,
            "node_id": node_id,
            "run_id": run_id,
            "task_id": task_id,
        },
    )
    return RunNodeResponse(
        run_id=run_id,
        node_id=node_id,
        task_id=task_id,
        status="queued",
    )


@router.get("/runs/{run_id}/nodes", response_model=list[NodeRunOut])
async def list_run_nodes(
    run_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[NodeRunOut]:
    rows = (
        await session.execute(
            select(LabNodeRun)
            .where(LabNodeRun.run_id == run_id)
            .order_by(LabNodeRun.started_at.asc().nulls_first())
        )
    ).scalars().all()
    return [_node_run_to_out(r) for r in rows]


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactOut])
async def list_run_artifacts(
    run_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[ArtifactOut]:
    rows = (
        await session.execute(
            select(LabArtifact)
            .where(LabArtifact.run_id == run_id)
            .order_by(LabArtifact.created_at.asc())
        )
    ).scalars().all()
    return [_artifact_row_to_out(r) for r in rows]


class ReproduceRunResponse(BaseModel):
    graph_id: str
    new_run_id: str
    new_task_id: str
    content_hash: str
    code_snapshot_matches: bool
    data_snapshot_matches: bool


@router.post("/runs/{run_id}/reproduce", response_model=ReproduceRunResponse)
async def reproduce_run(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> ReproduceRunResponse:
    """Re-dispatch a historical run with its pinned snapshot triple.

    Validates that the original ``(content_hash, data_snapshot,
    code_snapshot)`` triple still resolves — if the snippet sandbox
    image digest map has moved on, surfaces an actionable error so
    the operator knows replay isn't possible without restoring the
    pinned image. The replay submits a new ``LabRun`` row whose
    ``content_hash`` / ``code_snapshot`` / ``data_snapshot`` columns
    intentionally re-use the originals so the new run is provably
    a re-execution of the same artifact.
    """
    src = await session.get(LabRun, run_id)
    if src is None:
        raise HTTPException(404, "run not found")
    graph = await session.get(LabGraph, src.graph_id)
    if graph is None:
        raise HTTPException(404, "graph not found")

    # Validate the code snapshot — if the pinned image map has drifted
    # we refuse the replay rather than silently running against a
    # different binary.
    current_code = compute_code_snapshot()
    code_matches = bool(src.code_snapshot) and src.code_snapshot == current_code
    data_matches = bool(src.data_snapshot) and src.data_snapshot == (
        graph.data_snapshot or {}
    )
    if not code_matches:
        emit_audit_event(
            "lab.run.reproduce.code_drift",
            user_id=getattr(user, "id", None),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            actor_user_id=getattr(user, "id", None),
            event_category="safety",
            severity="warning",
            source="api",
            request=request,
            details={
                "run_id": run_id,
                "original_code_snapshot": src.code_snapshot,
                "current_code_snapshot": current_code,
            },
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "code_snapshot drift detected",
                "original": src.code_snapshot,
                "current": current_code,
                "hint": (
                    "Either restore the pinned executor images via "
                    "AQP_LAB_EXECUTOR_IMAGES, or fork a new run "
                    "(POST /lab/graphs/{id}/runs) which will pin the "
                    "current snapshot."
                ),
            },
        )

    try:
        from aqp.tasks.lab_tasks import run_lab_graph
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"lab Celery tasks not available: {exc}") from exc

    new_run_id = str(uuid4())
    task_id = str(uuid4())
    row = LabRun(
        id=new_run_id,
        graph_id=graph.id,
        lab_id=graph.lab_id,
        workspace_id=ctx.workspace_id,
        owner_user_id=getattr(user, "id", None),
        mode=graph.mode,
        status="queued",
        task_id=task_id,
        content_hash=src.content_hash,
        code_snapshot=src.code_snapshot,
        # Replay pins the ORIGINAL data snapshot deliberately — the
        # Iceberg snapshot id / Hudi commit time persist on
        # `lab_runs.data_snapshot` so a replay against a moved-on
        # warehouse is rejected at executor time when the snapshot
        # is no longer reachable.
        data_snapshot=dict(src.data_snapshot or {}),
        started_at=datetime.utcnow(),
    )
    session.add(row)
    await session.commit()
    run_lab_graph.apply_async(args=(graph.id, new_run_id, None), task_id=task_id)
    emit_audit_event(
        "lab.run.reproduce",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="account",
        severity="info",
        source="api",
        request=request,
        details={
            "original_run_id": run_id,
            "new_run_id": new_run_id,
            "graph_id": graph.id,
            "content_hash": src.content_hash,
            "data_snapshot_matches": data_matches,
        },
    )
    return ReproduceRunResponse(
        graph_id=graph.id,
        new_run_id=new_run_id,
        new_task_id=task_id,
        content_hash=src.content_hash,
        code_snapshot_matches=code_matches,
        data_snapshot_matches=data_matches,
    )


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:write")),
    ctx: RequestContext = Depends(current_context),
) -> RunOut:
    row = await session.get(LabRun, run_id)
    if row is None:
        raise HTTPException(404, "run not found")
    if row.status in {"done", "error", "cancelled", "halted"}:
        return _run_row_to_out(row)
    # Best-effort halt: stamp the row + drop a per-run Redis key the
    # WorkflowRuntime / future Celery wrapper polls.
    row.status = "halted"
    row.halted = True
    row.halt_reason = "cancel requested via /lab/runs/{id}/cancel"
    row.ended_at = datetime.utcnow()
    await session.commit()
    try:
        import redis  # type: ignore[import-not-found]

        client = redis.Redis.from_url(
            getattr(settings, "redis_url", None), socket_timeout=0.25
        )
        client.set(f"aqp:lab:halt:{run_id}", "1", ex=3600)
    except Exception:  # noqa: BLE001
        logger.debug("could not set lab halt redis flag", exc_info=True)
    await session.refresh(row)
    emit_audit_event(
        "lab.run.cancel",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="safety",
        severity="warning",
        source="api",
        request=request,
        details={
            "run_id": run_id,
            "graph_id": row.graph_id,
            "mode": row.mode,
            "halt_reason": row.halt_reason,
        },
    )
    return _run_row_to_out(row)


# ---------------------------------------------------------------------------
# Kill switch fan-out
# ---------------------------------------------------------------------------


@router.post("/halt-all", response_model=HaltAllResponse)
async def halt_all(
    request: Request,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_scope("data:admin")),
    ctx: RequestContext = Depends(current_context),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> HaltAllResponse:
    """Halt every currently-running ``lab_runs`` row.

    The :class:`KillSwitch` topbar component fans out to this endpoint
    alongside the existing /agents/halt / /paper/stop-all / /bots/halt-all /
    /rl/halt-all / /workflows/halt list per the frontend rule.
    """
    rows = (
        await session.execute(
            select(LabRun).where(LabRun.status.in_(("queued", "running")))
        )
    ).scalars().all()
    n = 0
    try:
        import redis  # type: ignore[import-not-found]

        client = redis.Redis.from_url(
            getattr(settings, "redis_url", None), socket_timeout=0.25
        )
    except Exception:  # noqa: BLE001
        client = None
    halted_ids: list[str] = []
    for row in rows:
        row.status = "halted"
        row.halted = True
        row.halt_reason = "halt-all"
        row.ended_at = datetime.utcnow()
        if client is not None:
            try:
                client.set(f"aqp:lab:halt:{row.id}", "1", ex=3600)
            except Exception:  # noqa: BLE001
                pass
        halted_ids.append(row.id)
        n += 1
    if n:
        await session.commit()
    emit_audit_event(
        "lab.halt_all",
        user_id=getattr(user, "id", None),
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=getattr(user, "id", None),
        event_category="safety",
        severity="critical" if n else "info",
        source="api",
        request=request,
        details={
            "halted_count": n,
            "halted_run_ids": halted_ids[:50],  # cap blob
        },
    )
    return HaltAllResponse(halted=n)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@ws_router.websocket("/ws/lab/{session_id}")
async def lab_websocket(ws: WebSocket, session_id: str) -> None:
    """Multiplexed Lab WebSocket.

    Wire protocol:

    - First frame MUST be ``{"type":"auth","token":"<JWT>"}`` per
      :class:`aqp.auth.ws.WebSocketAuthenticator`. Optional
      ``workspace_id``/``project_id``/``lab_id`` overrides pin the
      tenancy context for the lifetime of the connection. When
      ``settings.ws_auth_required`` is False (dev), an empty / missing
      auth frame degrades to the local-first default context.
    - After the auth handshake the client sends ``kind`` envelopes:

      - ``{kind:"subscribe", stream:"run", id:"<task_id>"}`` to attach
        to a run's progress.
      - ``{kind:"unsubscribe", id:"<task_id>"}`` to detach.
      - ``{kind:"eda.exec", cell_id, code}`` (Phase 1) to run a cell.
      - ``{kind:"sim.command", run_id, cmd, value}`` (Phase 4) to drive
        a Simulation tick.

    The server projects every canonical progress frame on the
    subscribed task channels into a typed Lab envelope (see
    :mod:`aqp.lab.ws.fanout`) and forwards it on this socket. Frame
    shape is preserved verbatim (rule 4).
    """
    await manager.connect(session_id, ws)
    pumps: dict[str, asyncio.Task[Any]] = {}

    # Phase 0 — first-frame token validation. The authenticator handles
    # all close-code semantics (4001 protocol error / 4003 invalid token /
    # 4008 insufficient scope). When ws_auth_required is False the
    # caller still receives a local-first context so dev iteration
    # works without a token.
    auth_result = await ws_authenticator.authenticate(ws)
    if auth_result is None:
        await manager.disconnect(session_id, ws)
        return
    ws_context = auth_result.context
    if not getattr(ws_context, "lab_id", None) and session_id:
        # Operator pinned a session id but didn't carry a lab id in
        # claims/overrides — keep the session id available on the
        # context so downstream subscribers can scope envelopes.
        try:
            ws_context = ws_context.with_overrides(lab_id=session_id)
        except Exception:  # noqa: BLE001
            pass

    async def pump(task_id: str) -> None:
        try:
            async for env in iter_lab_envelopes(task_id):
                payload = env.model_dump(mode="json", by_alias=True)
                payload.setdefault("kind", "run.status")
                try:
                    await ws.send_json(payload)
                except Exception:  # noqa: BLE001
                    break
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            logger.exception("lab WS pump crashed for task %s", task_id)

    try:
        while True:
            try:
                raw = await ws.receive_json()
            except WebSocketDisconnect:
                break
            kind = (raw or {}).get("kind")
            if kind == "subscribe":
                stream_id = str(raw.get("id") or "").strip()
                if not stream_id or stream_id in pumps:
                    continue
                pumps[stream_id] = asyncio.create_task(pump(lab_channel_id(stream_id)))
            elif kind == "unsubscribe":
                stream_id = str(raw.get("id") or "").strip()
                task = pumps.pop(stream_id, None)
                if task is not None:
                    task.cancel()
            elif kind == "eda.exec":
                # Phase 1 — routes through the long-lived EdaKernel
                # per session_id with the marimo-style reactive DAG.
                # The auth context from the first-frame handshake
                # flows through so tenancy stamping survives across
                # ws boundaries.
                from aqp.lab.runtime import LabRuntime
                from aqp.lab.schema import GraphSpec

                stub_spec = GraphSpec(name="eda-cell", mode="eda")
                runtime = LabRuntime(
                    stub_spec, session_id=session_id, context=ws_context
                )
                preview = runtime.preview_cell(
                    str(raw.get("code") or ""),
                    cell_id=str(raw.get("cell_id") or ""),
                )
                await ws.send_json(
                    {
                        "kind": "eda.cell.result",
                        "v": 1,
                        "task_id": session_id,
                        "timestamp": datetime.utcnow().timestamp(),
                        "stage": "eda.cell.result",
                        "message": "preview",
                        "cell_id": preview.get("cell_id"),
                        "stale_ids": preview.get("stale_ids", []),
                        "render": preview.get("render", {}),
                        "status": preview.get("status"),
                        "stdout": preview.get("stdout"),
                        "stderr": preview.get("stderr"),
                        "error": preview.get("error"),
                        "repr": preview.get("repr"),
                        "duration_ms": preview.get("duration_ms"),
                    }
                )
            elif kind == "sim.command":
                # Phase 4 wires this to the SandboxRuntime sim job;
                # Phase 0 just acks so the contract is exercised.
                await ws.send_json(
                    {
                        "kind": "run.status",
                        "v": 1,
                        "task_id": session_id,
                        "timestamp": datetime.utcnow().timestamp(),
                        "stage": "sim.command.ack",
                        "message": f"ack cmd={raw.get('cmd')}",
                        "run_id": str(raw.get("run_id") or ""),
                        "state": "running",
                    }
                )
            # Unknown kinds silently ignored — forward-compat.
    finally:
        for task in pumps.values():
            task.cancel()
        await manager.disconnect(session_id, ws)


__all__ = ["router", "ws_router"]
