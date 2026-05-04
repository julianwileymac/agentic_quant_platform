"""``/users`` — user CRUD + memberships across all scopes."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.auth import CurrentUser, current_user
from aqp.config.defaults import ALL_ROLES, ALL_SCOPE_KINDS, SCOPE_GLOBAL
from aqp.persistence import async_session_dep
from aqp.persistence.models_tenancy import Membership, User

router = APIRouter(prefix="/users", tags=["tenancy"])


class UserIn(BaseModel):
    email: EmailStr
    display_name: str
    auth_subject: str | None = None
    auth_provider: str = "local"
    avatar_url: str | None = None
    meta: dict[str, Any] | None = None


class UserPatch(BaseModel):
    display_name: str | None = None
    status: str | None = None
    auth_subject: str | None = None
    avatar_url: str | None = None
    meta: dict[str, Any] | None = None


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    auth_provider: str
    auth_subject: str | None = None
    status: str
    avatar_url: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    last_login_at: datetime | None = None


class MembershipIn(BaseModel):
    scope_kind: str
    scope_id: str
    role: str = "viewer"
    live_control: bool = False


def _to_user(row: User) -> UserOut:
    return UserOut(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        auth_provider=row.auth_provider,
        auth_subject=row.auth_subject,
        status=row.status,
        avatar_url=row.avatar_url,
        meta=row.meta or {},
        created_at=row.created_at,
        last_login_at=row.last_login_at,
    )


@router.get("", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(async_session_dep),
) -> list[UserOut]:
    rows = (await session.execute(select(User).order_by(User.email))).scalars().all()
    return [_to_user(r) for r in rows]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserIn,
    session: AsyncSession = Depends(async_session_dep),
) -> UserOut:
    row = User(
        email=str(body.email),
        display_name=body.display_name,
        auth_subject=body.auth_subject,
        auth_provider=body.auth_provider,
        avatar_url=body.avatar_url,
        meta=body.meta or {},
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_user(row)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> UserOut:
    row = await session.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    return _to_user(row)


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: str,
    body: UserPatch,
    session: AsyncSession = Depends(async_session_dep),
) -> UserOut:
    row = await session.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_user(row)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    row = await session.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    await session.delete(row)
    await session.commit()


@router.get("/{user_id}/memberships")
async def list_user_memberships(
    user_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(select(Membership).where(Membership.user_id == user_id))
    ).scalars().all()
    return [
        {
            "id": m.id,
            "scope_kind": m.scope_kind,
            "scope_id": m.scope_id,
            "role": m.role,
            "live_control": m.live_control,
            "granted_at": m.granted_at,
        }
        for m in rows
    ]


@router.post("/{user_id}/memberships", status_code=status.HTTP_201_CREATED)
async def add_user_membership(
    user_id: str,
    body: MembershipIn,
    session: AsyncSession = Depends(async_session_dep),
    granter: CurrentUser = Depends(current_user),
) -> dict[str, str]:
    if body.role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ALL_ROLES}")
    if body.scope_kind not in {k for k in ALL_SCOPE_KINDS if k != SCOPE_GLOBAL}:
        raise HTTPException(status_code=400, detail=f"scope_kind must be one of {ALL_SCOPE_KINDS}")
    row = Membership(
        user_id=user_id,
        scope_kind=body.scope_kind,
        scope_id=body.scope_id,
        role=body.role,
        live_control=body.live_control,
        granted_by=granter.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {"membership_id": row.id}


@router.delete(
    "/{user_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def revoke_user_membership(
    user_id: str,
    membership_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    row = await session.get(Membership, membership_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="membership not found")
    await session.delete(row)
    await session.commit()
