"""``/orgs`` — organization CRUD + sub-resource listings.

Mirrors Lean's ``GET organizations/read`` shape (see
``inspiration/Lean-master/Common/Api/Organization.cs``) but stripped of
billing/credit semantics — those land in a future ``/billing`` surface.
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
from aqp.persistence.models_tenancy import (
    Membership,
    Organization,
    Team,
    Workspace,
)

router = APIRouter(prefix="/orgs", tags=["tenancy"])


class OrgIn(BaseModel):
    slug: str
    name: str
    billing_email: str | None = None
    meta: dict[str, Any] | None = None


class OrgPatch(BaseModel):
    name: str | None = None
    billing_email: str | None = None
    status: str | None = None
    meta: dict[str, Any] | None = None


class OrgOut(BaseModel):
    id: str
    slug: str
    name: str
    billing_email: str | None = None
    status: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


def _to_org(row: Organization) -> OrgOut:
    return OrgOut(
        id=row.id,
        slug=row.slug,
        name=row.name,
        billing_email=row.billing_email,
        status=row.status,
        meta=row.meta or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[OrgOut])
async def list_orgs(
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(current_user),
) -> list[OrgOut]:
    rows = (await session.execute(select(Organization).order_by(Organization.name))).scalars().all()
    return [_to_org(r) for r in rows]


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
async def create_org(
    body: OrgIn,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(current_user),
) -> OrgOut:
    row = Organization(
        slug=body.slug,
        name=body.name,
        billing_email=body.billing_email,
        meta=body.meta or {},
    )
    session.add(row)
    await session.flush()
    session.add(
        Membership(
            user_id=user.id,
            scope_kind="org",
            scope_id=row.id,
            role="owner",
            live_control=True,
            granted_by=user.id,
        )
    )
    await session.commit()
    await session.refresh(row)
    return _to_org(row)


@router.get("/{org_id}", response_model=OrgOut)
async def get_org(
    org_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> OrgOut:
    row = await session.get(Organization, org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="org not found")
    return _to_org(row)


@router.patch("/{org_id}", response_model=OrgOut)
async def patch_org(
    org_id: str,
    body: OrgPatch,
    session: AsyncSession = Depends(async_session_dep),
) -> OrgOut:
    row = await session.get(Organization, org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="org not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_org(row)


@router.delete(
    "/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_org(
    org_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    row = await session.get(Organization, org_id)
    if row is None:
        raise HTTPException(status_code=404, detail="org not found")
    await session.delete(row)
    await session.commit()


@router.get("/{org_id}/teams")
async def list_org_teams(
    org_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(select(Team).where(Team.org_id == org_id).order_by(Team.name))
    ).scalars().all()
    return [
        {"id": r.id, "slug": r.slug, "name": r.name, "description": r.description}
        for r in rows
    ]


@router.get("/{org_id}/workspaces")
async def list_org_workspaces(
    org_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Workspace).where(Workspace.org_id == org_id).order_by(Workspace.name)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "slug": r.slug,
            "name": r.name,
            "visibility": r.visibility,
            "archived": r.archived,
        }
        for r in rows
    ]
