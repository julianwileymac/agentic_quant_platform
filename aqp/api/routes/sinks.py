"""``/sinks`` REST surface.

CRUD over the project-scoped sink registry plus a ``/sinks/kinds``
catalog endpoint that the SinkRegistry UI uses to render its kind
picker. Every edit re-snapshots the spec into an immutable
:class:`SinkVersionRow` (mirroring the ``bot_versions`` /
``agent_spec_versions`` pattern).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from aqp.auth.context import RequestContext
from aqp.auth.deps import current_context
from aqp.data.fetchers.sinks import list_sink_kinds
from aqp.data.sinks import (
    SinkNotFoundError,
    SinkValidationError,
    create_sink,
    delete_sink,
    get_sink,
    list_sink_versions,
    list_sinks,
    materialise_node_spec,
    sink_summary,
    update_sink,
)
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sinks", tags=["sinks"])


class SinkKindView(BaseModel):
    kind: str
    display_name: str
    description: str
    config_fields: list[dict[str, Any]] = Field(default_factory=list)
    default_node_template: dict[str, Any] = Field(default_factory=dict)
    supported_domains: list[str] = Field(default_factory=list)
    documentation_url: str | None = None
    tags: list[str] = Field(default_factory=list)


class SinkSummaryView(BaseModel):
    id: str
    name: str
    kind: str
    display_name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    documentation_url: str | None = None
    requires_manifest_node: bool = True
    current_version: int = 1
    enabled: bool = True
    annotations: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    owner_user_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SinkVersionView(BaseModel):
    id: str
    sink_id: str
    version: int
    spec_hash: str
    payload: dict[str, Any]
    notes: str | None = None
    created_by: str | None = None
    created_at: str | None = None


class CreateSinkRequest(BaseModel):
    name: str
    kind: str
    display_name: str | None = None
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    documentation_url: str | None = None
    requires_manifest_node: bool = True
    enabled: bool = True
    annotations: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class UpdateSinkRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    tags: list[str] | None = None
    documentation_url: str | None = None
    requires_manifest_node: bool | None = None
    enabled: bool | None = None
    annotations: list[str] | None = None
    meta: dict[str, Any] | None = None
    notes: str | None = None


class MaterialiseRequest(BaseModel):
    overrides: dict[str, Any] = Field(default_factory=dict)


class MaterialiseResponse(BaseModel):
    name: str
    kwargs: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None
    enabled: bool = True


@router.get("/kinds", response_model=list[SinkKindView])
def list_kinds() -> list[SinkKindView]:
    """Return the catalog of supported sink kinds (UI kind picker)."""
    return [SinkKindView(**desc.to_dict()) for desc in list_sink_kinds()]


@router.get("/", response_model=list[SinkSummaryView])
def list_endpoint(
    kind: str | None = None,
    enabled_only: bool = False,
    limit: int | None = None,
    ctx: RequestContext = Depends(current_context),
) -> list[SinkSummaryView]:
    with get_session() as session:
        rows = list_sinks(
            session,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
            kind=kind,
            enabled_only=enabled_only,
            limit=limit,
        )
        return [SinkSummaryView(**sink_summary(r)) for r in rows]


@router.post("/", response_model=SinkSummaryView, status_code=201)
def create_endpoint(
    body: CreateSinkRequest,
    ctx: RequestContext = Depends(current_context),
) -> SinkSummaryView:
    with get_session() as session:
        try:
            row = create_sink(
                session,
                name=body.name,
                kind=body.kind,
                display_name=body.display_name,
                description=body.description,
                config=body.config,
                tags=body.tags,
                documentation_url=body.documentation_url,
                requires_manifest_node=body.requires_manifest_node,
                enabled=body.enabled,
                annotations=body.annotations,
                meta=body.meta,
                owner_user_id=ctx.user_id,
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
                created_by=ctx.user_id,
                notes=body.notes,
            )
            session.commit()
        except SinkValidationError as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SinkSummaryView(**sink_summary(row))


@router.get("/{sink_id}", response_model=SinkSummaryView)
def get_endpoint(sink_id: str) -> SinkSummaryView:
    with get_session() as session:
        try:
            row = get_sink(session, sink_id)
        except SinkNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return SinkSummaryView(**sink_summary(row))


@router.patch("/{sink_id}", response_model=SinkSummaryView)
def patch_endpoint(
    sink_id: str,
    body: UpdateSinkRequest,
    ctx: RequestContext = Depends(current_context),
) -> SinkSummaryView:
    with get_session() as session:
        try:
            row = update_sink(
                session,
                sink_id,
                display_name=body.display_name,
                description=body.description,
                config=body.config,
                tags=body.tags,
                documentation_url=body.documentation_url,
                requires_manifest_node=body.requires_manifest_node,
                enabled=body.enabled,
                annotations=body.annotations,
                meta=body.meta,
                notes=body.notes,
                created_by=ctx.user_id,
            )
            session.commit()
        except SinkNotFoundError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SinkValidationError as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SinkSummaryView(**sink_summary(row))


@router.delete("/{sink_id}", status_code=204, response_class=Response)
def delete_endpoint(sink_id: str) -> Response:
    with get_session() as session:
        try:
            delete_sink(session, sink_id)
            session.commit()
        except SinkNotFoundError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/{sink_id}/versions", response_model=list[SinkVersionView])
def list_versions_endpoint(sink_id: str) -> list[SinkVersionView]:
    with get_session() as session:
        try:
            get_sink(session, sink_id)
        except SinkNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        rows = list_sink_versions(session, sink_id)
        return [
            SinkVersionView(
                id=v.id,
                sink_id=v.sink_id,
                version=int(v.version),
                spec_hash=v.spec_hash,
                payload=dict(v.payload or {}),
                notes=v.notes,
                created_by=v.created_by,
                created_at=v.created_at.isoformat() if v.created_at else None,
            )
            for v in rows
        ]


@router.post("/{sink_id}/materialise", response_model=MaterialiseResponse)
def materialise_endpoint(
    sink_id: str,
    body: MaterialiseRequest | None = None,
) -> MaterialiseResponse:
    """Resolve a sink into a manifest-ready :class:`NodeSpec` JSON dict."""
    body = body or MaterialiseRequest()
    with get_session() as session:
        try:
            spec = materialise_node_spec(session, sink_id, overrides=body.overrides)
        except SinkNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return MaterialiseResponse(
            name=spec.name, kwargs=spec.kwargs, label=spec.label, enabled=spec.enabled
        )


__all__ = ["router"]
