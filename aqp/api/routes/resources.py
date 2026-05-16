"""``/resources`` — polymorphic asset registry CRUD.

Every content asset that isn't already a first-class ORM (datasets get
their own, bots get their own, etc.) lives here so the MCP catalog,
EntityPicker, and ownership graph can iterate them uniformly. The
Phase 7 LEAN ingester writes here; the Phase 2 Neo4j projector mirrors
``resources`` + ``resource_relations`` into the ownership graph.

Ownership is polymorphic: the ``owner_scope_kind`` /
``owner_scope_id`` pair points at an Organization / Team / Workspace /
Project / User. Visibility rules:

- ``user``  -> visible only to that user.
- ``team``  -> visible to every member of that team.
- ``workspace`` -> follows the workspace's visibility (private / team / org).
- ``project`` -> visible to every member of the project.
- ``organization`` -> visible to every member of the org.

Phase 4 will tighten the read filters with ``data.ownership.*`` MCP
tool semantics; this route currently delegates the read check to the
DB query joined with ``Membership``.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.auth import (
    CurrentUser,
    RequestContext,
    current_context,
    require_authenticated,
)
from aqp.persistence import async_session_dep
from aqp.persistence.models_resources import (
    OWNER_SCOPE_KINDS,
    RESOURCE_RELATIONS,
    RESOURCE_TYPES,
    Resource,
    ResourceRelation,
)

router = APIRouter(prefix="/resources", tags=["resources"])


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower().strip()).strip("-")
    return base[:180] or "resource"


class ResourceIn(BaseModel):
    name: str
    resource_type: str
    slug: str | None = None
    uri: str | None = None
    description: str | None = None
    owner_scope_kind: str | None = None
    owner_scope_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    visibility: str = "private"


class ResourcePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    uri: str | None = None
    meta: dict[str, Any] | None = None
    tags: list[str] | None = None
    visibility: str | None = None


class ResourceOut(BaseModel):
    id: str
    name: str
    slug: str
    resource_type: str
    uri: str | None = None
    description: str | None = None
    owner_scope_kind: str
    owner_scope_id: str
    workspace_id: str | None = None
    project_id: str | None = None
    owner_user_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    visibility: str
    created_at: datetime
    updated_at: datetime


class RelationIn(BaseModel):
    from_id: str
    to_id: str
    relation: str = "uses"
    details: dict[str, Any] = Field(default_factory=dict)


class RelationOut(BaseModel):
    id: str
    from_id: str
    to_id: str
    relation: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


def _to_out(row: Resource) -> ResourceOut:
    return ResourceOut(
        id=row.id,
        name=row.name,
        slug=row.slug,
        resource_type=row.resource_type,
        uri=row.uri,
        description=row.description,
        owner_scope_kind=row.owner_scope_kind,
        owner_scope_id=row.owner_scope_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        owner_user_id=row.owner_user_id,
        meta=dict(row.meta or {}),
        tags=list(row.tags or []),
        visibility=row.visibility,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _rel_out(row: ResourceRelation) -> RelationOut:
    return RelationOut(
        id=row.id,
        from_id=row.from_id,
        to_id=row.to_id,
        relation=row.relation,
        details=dict(row.details or {}),
        created_at=row.created_at,
    )


@router.get("", response_model=list[ResourceOut])
async def list_resources(
    resource_type: str | None = None,
    owner_scope_kind: str | None = None,
    owner_scope_id: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
    visibility: str | None = None,
    limit: int = 200,
    session: AsyncSession = Depends(async_session_dep),
    ctx: RequestContext = Depends(current_context),
    _: CurrentUser = Depends(require_authenticated),
) -> list[ResourceOut]:
    stmt = select(Resource).order_by(Resource.updated_at.desc()).limit(limit)
    if resource_type:
        stmt = stmt.where(Resource.resource_type == resource_type)
    if owner_scope_kind:
        stmt = stmt.where(Resource.owner_scope_kind == owner_scope_kind)
    if owner_scope_id:
        stmt = stmt.where(Resource.owner_scope_id == owner_scope_id)
    target_ws = workspace_id or ctx.workspace_id
    if target_ws:
        stmt = stmt.where(Resource.workspace_id == target_ws)
    target_proj = project_id or ctx.project_id
    if target_proj:
        stmt = stmt.where(Resource.project_id == target_proj)
    if visibility:
        stmt = stmt.where(Resource.visibility == visibility)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
async def create_resource(
    body: ResourceIn,
    session: AsyncSession = Depends(async_session_dep),
    ctx: RequestContext = Depends(current_context),
    user: CurrentUser = Depends(require_authenticated),
) -> ResourceOut:
    if body.resource_type not in RESOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"resource_type must be one of {RESOURCE_TYPES}",
        )
    owner_kind = body.owner_scope_kind or "user"
    if owner_kind not in OWNER_SCOPE_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"owner_scope_kind must be one of {OWNER_SCOPE_KINDS}",
        )
    owner_id = body.owner_scope_id or {
        "user": user.id,
        "organization": ctx.org_id,
        "team": ctx.team_id,
        "workspace": ctx.workspace_id,
        "project": ctx.project_id,
    }.get(owner_kind)
    if not owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"owner_scope_id required when owner_scope_kind={owner_kind!r} "
                "and the active context has no matching id"
            ),
        )
    row = Resource(
        name=body.name,
        slug=body.slug or _slugify(body.name),
        resource_type=body.resource_type,
        uri=body.uri,
        description=body.description,
        owner_scope_kind=owner_kind,
        owner_scope_id=owner_id,
        meta=dict(body.meta or {}),
        tags=list(body.tags or []),
        visibility=body.visibility,
        owner_user_id=user.id,
        workspace_id=ctx.workspace_id,
        project_id=ctx.project_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    try:
        from aqp.cache import cache_write_through

        cache_write_through(
            "resources",
            {
                "id": row.id,
                "name": row.name,
                "slug": row.slug,
                "resource_type": row.resource_type,
                "owner_scope_kind": row.owner_scope_kind,
                "owner_scope_id": row.owner_scope_id,
            },
        )
    except Exception:  # noqa: BLE001
        # Cache write-through is a UX optimisation; never block on it.
        # Phase 5 adds the ``resources`` category to CACHE_CATEGORIES
        # at which point this call becomes effective; for now the
        # category may not exist and the helper logs and skips.
        pass

    return _to_out(row)


@router.get("/{resource_id}", response_model=ResourceOut)
async def get_resource(
    resource_id: str,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> ResourceOut:
    row = await session.get(Resource, resource_id)
    if row is None:
        raise HTTPException(status_code=404, detail="resource not found")
    return _to_out(row)


@router.patch("/{resource_id}", response_model=ResourceOut)
async def patch_resource(
    resource_id: str,
    body: ResourcePatch,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> ResourceOut:
    row = await session.get(Resource, resource_id)
    if row is None:
        raise HTTPException(status_code=404, detail="resource not found")
    payload = body.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(row, field, value)
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.delete(
    "/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_resource(
    resource_id: str,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> None:
    row = await session.get(Resource, resource_id)
    if row is None:
        raise HTTPException(status_code=404, detail="resource not found")
    await session.delete(row)
    await session.commit()


@router.get("/{resource_id}/relations", response_model=list[RelationOut])
async def list_resource_relations(
    resource_id: str,
    direction: str = "both",
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> list[RelationOut]:
    """Return edges touching this resource (``both``, ``incoming``, ``outgoing``)."""
    stmt = select(ResourceRelation)
    if direction == "outgoing":
        stmt = stmt.where(ResourceRelation.from_id == resource_id)
    elif direction == "incoming":
        stmt = stmt.where(ResourceRelation.to_id == resource_id)
    else:
        stmt = stmt.where(
            (ResourceRelation.from_id == resource_id)
            | (ResourceRelation.to_id == resource_id)
        )
    rows = (await session.execute(stmt.order_by(ResourceRelation.created_at.desc()))).scalars().all()
    return [_rel_out(r) for r in rows]


@router.post("/relations", response_model=RelationOut, status_code=status.HTTP_201_CREATED)
async def create_resource_relation(
    body: RelationIn,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> RelationOut:
    if body.relation not in RESOURCE_RELATIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"relation must be one of {RESOURCE_RELATIONS}",
        )
    row = ResourceRelation(
        from_id=body.from_id,
        to_id=body.to_id,
        relation=body.relation,
        details=dict(body.details or {}),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _rel_out(row)


__all__ = [
    "RelationIn",
    "RelationOut",
    "ResourceIn",
    "ResourceOut",
    "ResourcePatch",
    "router",
]
