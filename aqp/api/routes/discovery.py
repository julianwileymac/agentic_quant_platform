"""Active discovery REST surface (phase 1 of the data fabric)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from aqp.auth.context import RequestContext
from aqp.auth.deps import current_context
from aqp.data.discovery import DiscoveryService
from aqp.data.discovery.types import (
    CreateExternalEntryRequest,
    DiscoveryEntry,
    DiscoveryLifecycleState,
    DiscoveryPage,
    PromoteRequest,
    PromoteResponse,
    UpdateEntryRequest,
)

router = APIRouter(prefix="/discovery", tags=["discovery"])

_service = DiscoveryService()


@router.get("/entries", response_model=DiscoveryPage)
def list_entries(
    lifecycle: DiscoveryLifecycleState | None = Query(default=None),
    provider: str | None = Query(default=None),
    kind: str | None = Query(default=None, description="Filter by dataset_kind"),
    search: str | None = Query(default=None, max_length=120),
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> DiscoveryPage:
    return _service.list(
        lifecycle=lifecycle,
        provider=provider,
        kind=kind,
        search=search,
        cursor=cursor,
        limit=limit,
    )


@router.get("/entries/{entry_id}", response_model=DiscoveryEntry)
def get_entry(entry_id: str) -> DiscoveryEntry:
    entry = _service.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"discovery entry {entry_id!r} not found")
    return entry


@router.post("/entries", response_model=DiscoveryEntry, status_code=201)
def create_entry(
    payload: CreateExternalEntryRequest,
    ctx: RequestContext = Depends(current_context),
) -> DiscoveryEntry:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    return _service.create_external(
        payload,
        owner_user_id=ctx.user_id,
        workspace_id=ctx.workspace_id,
        project_id=ctx.project_id,
    )


@router.patch("/entries/{entry_id}", response_model=DiscoveryEntry)
def patch_entry(entry_id: str, payload: UpdateEntryRequest) -> DiscoveryEntry:
    if not entry_id or entry_id.startswith(("orphan:", "library:", "airbyte:")):
        raise HTTPException(
            status_code=409,
            detail="virtual entries must be promoted before they can be edited",
        )
    entry = _service.patch(entry_id, payload)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"discovery entry {entry_id!r} not found")
    return entry


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: str) -> dict[str, Any]:
    if not entry_id or entry_id.startswith(("orphan:", "library:", "airbyte:")):
        raise HTTPException(
            status_code=409,
            detail="virtual entries cannot be deleted from the discovery surface",
        )
    try:
        deleted = _service.delete(entry_id)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"discovery entry {entry_id!r} not found")
    return {"deleted": entry_id}


@router.post("/entries/{entry_id}/promote", response_model=PromoteResponse)
def promote_entry(
    entry_id: str,
    payload: PromoteRequest,
    ctx: RequestContext = Depends(current_context),
) -> PromoteResponse:
    try:
        result = _service.promote(
            entry_id,
            target_kind=payload.target_kind,
            notes=payload.notes,
            actor=ctx.user_id,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PromoteResponse(**result)


@router.get("/entries/{entry_id}/lineage")
def entry_lineage(entry_id: str) -> dict[str, Any]:
    if entry_id.startswith(("orphan:", "library:", "airbyte:")):
        return {"dataset": None, "nodes": [], "edges": []}
    from aqp.services.metadata_catalog_service import MetadataCatalogService

    return MetadataCatalogService().lineage(entry_id)
