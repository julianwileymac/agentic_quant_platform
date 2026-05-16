"""``/strategies/templates`` — REST surface for the LEAN template catalog.

Mirrors the ``data.strategies.templates.*`` MCP tools so the frontend
template browser doesn't have to round-trip through MCP. The mounted
router enforces :func:`aqp.api.security.require_authenticated` on
every endpoint (clone-to-workspace also wants ``data:write``).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.api.security import require_authenticated, require_scope
from aqp.auth import CurrentUser, RequestContext, current_context
from aqp.persistence import async_session_dep
from aqp.persistence.models_resources import Resource, ResourceRelation

router = APIRouter(prefix="/strategies/templates", tags=["strategies", "templates"])


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower().strip()).strip("-")
    return base[:180] or "template"


class TemplateSummary(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None
    uri: str | None = None
    tags: list[str] = Field(default_factory=list)
    asset_classes: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    framework: str = "lean"
    class_name: str | None = None
    source_path: str | None = None


class TemplateDetail(TemplateSummary):
    raw_source: str | None = None


class CloneRequest(BaseModel):
    template_id: str
    new_slug: str | None = None
    translate: bool = True


class CloneResponse(BaseModel):
    id: str
    slug: str
    translated: bool
    source_id: str | None = None


def _row_to_summary(row: Resource) -> TemplateSummary:
    meta = dict(row.meta or {})
    return TemplateSummary(
        id=row.id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        uri=row.uri,
        tags=list(row.tags or []),
        asset_classes=list(meta.get("asset_classes") or []),
        indicators=list(meta.get("indicators") or []),
        framework=str(meta.get("framework") or "lean"),
        class_name=meta.get("class_name"),
        source_path=meta.get("source_path"),
    )


def _row_to_detail(row: Resource) -> TemplateDetail:
    summary = _row_to_summary(row)
    meta = dict(row.meta or {})
    return TemplateDetail(**summary.model_dump(), raw_source=meta.get("raw_source"))


@router.get("", response_model=list[TemplateSummary])
async def list_templates(
    asset_class: str | None = None,
    tag: str | None = None,
    framework: str | None = None,
    search: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> list[TemplateSummary]:
    stmt = (
        select(Resource)
        .where(Resource.resource_type == "strategy_template")
        .order_by(Resource.name)
        .limit(limit)
    )
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            (Resource.name.ilike(like)) | (Resource.description.ilike(like))
        )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[TemplateSummary] = []
    for row in rows:
        summary = _row_to_summary(row)
        if asset_class and asset_class not in (summary.asset_classes or []):
            continue
        if tag and tag not in (summary.tags or []):
            continue
        if framework and summary.framework != framework:
            continue
        out.append(summary)
    return out


@router.get("/{template_id}", response_model=TemplateDetail)
async def describe_template(
    template_id: str,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> TemplateDetail:
    row = await session.get(Resource, template_id)
    if row is None:
        stmt = (
            select(Resource)
            .where(Resource.resource_type == "strategy_template")
            .where(Resource.slug == template_id)
        )
        row = (await session.execute(stmt)).scalars().first()
    if row is None or row.resource_type != "strategy_template":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="template not found"
        )
    return _row_to_detail(row)


@router.post("/clone", response_model=CloneResponse, status_code=status.HTTP_201_CREATED)
async def clone_template(
    body: CloneRequest,
    session: AsyncSession = Depends(async_session_dep),
    ctx: RequestContext = Depends(current_context),
    user: CurrentUser = Depends(require_scope("data:write")),
) -> CloneResponse:
    source = await session.get(Resource, body.template_id)
    if source is None:
        stmt = (
            select(Resource)
            .where(Resource.resource_type == "strategy_template")
            .where(Resource.slug == body.template_id)
        )
        source = (await session.execute(stmt)).scalars().first()
    if source is None or source.resource_type != "strategy_template":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="template not found"
        )
    source_meta = dict(source.meta or {})
    raw_source = source_meta.get("raw_source", "")
    payload = raw_source
    translated = False
    if body.translate and raw_source:
        from aqp.strategies.lean.translator import translate_lean_to_framework

        payload = translate_lean_to_framework(
            raw_source, class_name=source_meta.get("class_name")
        )
        translated = True

    slug = body.new_slug or _slugify(f"{source.slug}-clone")
    cloned = Resource(
        name=f"{source.name} (cloned)",
        slug=slug,
        resource_type="strategy_template",
        uri=f"workspace://{ctx.workspace_id or 'default'}/{slug}",
        description=source.description,
        owner_scope_kind="user",
        owner_scope_id=user.id,
        meta={
            **source_meta,
            "raw_source": payload,
            "translated_from_lean": translated,
            "cloned_from": source.id,
        },
        tags=list(source.tags or []),
        visibility="private",
        owner_user_id=user.id,
        workspace_id=ctx.workspace_id,
        project_id=ctx.project_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(cloned)
    await session.flush()

    session.add(
        ResourceRelation(
            from_id=cloned.id,
            to_id=source.id,
            relation="translated_from" if translated else "clones",
            details={"translated": translated},
            created_at=datetime.utcnow(),
        )
    )
    await session.commit()

    return CloneResponse(
        id=cloned.id,
        slug=cloned.slug,
        translated=translated,
        source_id=source.id,
    )


__all__ = ["CloneRequest", "CloneResponse", "TemplateDetail", "TemplateSummary", "router"]
