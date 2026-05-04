"""``/labs`` — interactive-research lab CRUD + per-lab artifact listings.

A Lab is the AQP analog of Lean's :class:`QuantBook` (research mode +
notebook-style state). Lean folds research into the same ``Project``
container; we keep them as separate entities so the UI can present
distinct surfaces (`/projects` vs `/labs`).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.auth import CurrentUser, current_user
from aqp.persistence import async_session_dep
from aqp.persistence.models_memory import MemoryEpisode
from aqp.persistence.models_rag import RagCorpus
from aqp.persistence.models_tenancy import Lab, Membership

router = APIRouter(prefix="/labs", tags=["tenancy"])


class LabIn(BaseModel):
    workspace_id: str
    slug: str
    name: str
    description: str | None = None
    kernel_image: str | None = None
    settings: dict[str, Any] | None = None


class LabPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    kernel_image: str | None = None
    archived: bool | None = None
    settings: dict[str, Any] | None = None


class LabOut(BaseModel):
    id: str
    workspace_id: str
    slug: str
    name: str
    description: str | None = None
    kernel_image: str | None = None
    archived: bool
    last_active_at: datetime | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


def _to_lab(row: Lab) -> LabOut:
    return LabOut(
        id=row.id,
        workspace_id=row.workspace_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        kernel_image=row.kernel_image,
        archived=row.archived,
        last_active_at=row.last_active_at,
        settings=row.settings or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[LabOut])
async def list_labs(
    workspace_id: str | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> list[LabOut]:
    stmt = select(Lab).order_by(Lab.name)
    if workspace_id:
        stmt = stmt.where(Lab.workspace_id == workspace_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_lab(r) for r in rows]


@router.post("", response_model=LabOut, status_code=status.HTTP_201_CREATED)
async def create_lab(
    body: LabIn,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(current_user),
) -> LabOut:
    row = Lab(
        workspace_id=body.workspace_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        kernel_image=body.kernel_image,
        settings=body.settings or {},
    )
    session.add(row)
    await session.flush()
    session.add(
        Membership(
            user_id=user.id,
            scope_kind="lab",
            scope_id=row.id,
            role="owner",
            live_control=True,
            granted_by=user.id,
        )
    )
    await session.commit()
    await session.refresh(row)
    return _to_lab(row)


@router.get("/{lab_id}", response_model=LabOut)
async def get_lab(
    lab_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> LabOut:
    row = await session.get(Lab, lab_id)
    if row is None:
        raise HTTPException(status_code=404, detail="lab not found")
    return _to_lab(row)


@router.patch("/{lab_id}", response_model=LabOut)
async def patch_lab(
    lab_id: str,
    body: LabPatch,
    session: AsyncSession = Depends(async_session_dep),
) -> LabOut:
    row = await session.get(Lab, lab_id)
    if row is None:
        raise HTTPException(status_code=404, detail="lab not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_lab(row)


@router.delete(
    "/{lab_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_lab(
    lab_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    row = await session.get(Lab, lab_id)
    if row is None:
        raise HTTPException(status_code=404, detail="lab not found")
    await session.delete(row)
    await session.commit()


@router.post("/{lab_id}/touch", response_model=LabOut)
async def touch_lab(
    lab_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> LabOut:
    """Stamp ``last_active_at`` to record kernel activity."""
    row = await session.get(Lab, lab_id)
    if row is None:
        raise HTTPException(status_code=404, detail="lab not found")
    row.last_active_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_lab(row)


@router.get("/{lab_id}/corpora")
async def list_lab_corpora(
    lab_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(RagCorpus).where(RagCorpus.lab_id == lab_id).order_by(RagCorpus.name)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "order": r.order,
            "l1": r.l1,
            "l2": r.l2,
            "chunks_count": r.chunks_count,
        }
        for r in rows
    ]


@router.get("/{lab_id}/memory")
async def list_lab_memory(
    lab_id: str,
    session: AsyncSession = Depends(async_session_dep),
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(MemoryEpisode)
            .where(MemoryEpisode.lab_id == lab_id)
            .order_by(MemoryEpisode.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "role": r.role,
            "vt_symbol": r.vt_symbol,
            "situation": (r.situation or "")[:200],
            "lesson": (r.lesson or "")[:200],
            "created_at": r.created_at,
        }
        for r in rows
    ]
