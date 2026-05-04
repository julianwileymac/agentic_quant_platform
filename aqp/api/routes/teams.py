"""``/teams`` — team CRUD + member management."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.auth import CurrentUser, current_user
from aqp.config.defaults import ALL_ROLES
from aqp.persistence import async_session_dep
from aqp.persistence.models_tenancy import Membership, Team, User

router = APIRouter(prefix="/teams", tags=["tenancy"])


class TeamIn(BaseModel):
    org_id: str
    slug: str
    name: str
    description: str | None = None
    meta: dict[str, Any] | None = None


class TeamPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    meta: dict[str, Any] | None = None


class TeamOut(BaseModel):
    id: str
    org_id: str
    slug: str
    name: str
    description: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MemberIn(BaseModel):
    user_id: str
    role: str = "viewer"
    live_control: bool = False


def _to_team(row: Team) -> TeamOut:
    return TeamOut(
        id=row.id,
        org_id=row.org_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        meta=row.meta or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[TeamOut])
async def list_teams(
    org_id: str | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> list[TeamOut]:
    stmt = select(Team).order_by(Team.name)
    if org_id:
        stmt = stmt.where(Team.org_id == org_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_team(r) for r in rows]


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamIn,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(current_user),
) -> TeamOut:
    row = Team(
        org_id=body.org_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        meta=body.meta or {},
    )
    session.add(row)
    await session.flush()
    session.add(
        Membership(
            user_id=user.id,
            scope_kind="team",
            scope_id=row.id,
            role="owner",
            live_control=True,
            granted_by=user.id,
        )
    )
    await session.commit()
    await session.refresh(row)
    return _to_team(row)


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> TeamOut:
    row = await session.get(Team, team_id)
    if row is None:
        raise HTTPException(status_code=404, detail="team not found")
    return _to_team(row)


@router.patch("/{team_id}", response_model=TeamOut)
async def patch_team(
    team_id: str,
    body: TeamPatch,
    session: AsyncSession = Depends(async_session_dep),
) -> TeamOut:
    row = await session.get(Team, team_id)
    if row is None:
        raise HTTPException(status_code=404, detail="team not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_team(row)


@router.delete(
    "/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_team(
    team_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    row = await session.get(Team, team_id)
    if row is None:
        raise HTTPException(status_code=404, detail="team not found")
    await session.delete(row)
    await session.commit()


@router.get("/{team_id}/members")
async def list_team_members(
    team_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.scope_kind == "team", Membership.scope_id == team_id)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "membership_id": m.id,
            "user_id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "role": m.role,
            "live_control": m.live_control,
            "granted_at": m.granted_at,
        }
        for m, u in rows
    ]


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: str,
    body: MemberIn,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(current_user),
) -> dict[str, str]:
    if body.role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ALL_ROLES}")
    row = Membership(
        user_id=body.user_id,
        scope_kind="team",
        scope_id=team_id,
        role=body.role,
        live_control=body.live_control,
        granted_by=user.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {"membership_id": row.id}


@router.delete(
    "/{team_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def remove_team_member(
    team_id: str,
    user_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    stmt = select(Membership).where(
        Membership.scope_kind == "team",
        Membership.scope_id == team_id,
        Membership.user_id == user_id,
    )
    rows = (await session.execute(stmt)).scalars().all()
    for r in rows:
        await session.delete(r)
    await session.commit()
