"""``/workspaces`` — workspace CRUD + project/lab listings + collaborators.

Mirrors the Lean ``Project`` REST shape but moved up to the workspace
level (Lean conflates project + container). Lean reference:
``inspiration/Lean-master/Common/Api/Project.cs`` and
``Api/Api.cs`` (``projects/create``, ``projects/read``,
``projects/nodes/read``, ``projects/nodes/update``).
"""
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
from aqp.persistence.models_tenancy import (
    Lab,
    Membership,
    Project,
    User,
    Workspace,
)

router = APIRouter(prefix="/workspaces", tags=["tenancy"])


class WorkspaceIn(BaseModel):
    org_id: str
    slug: str
    name: str
    description: str | None = None
    visibility: str = "team"
    settings: dict[str, Any] | None = None


class WorkspacePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    visibility: str | None = None
    archived: bool | None = None
    settings: dict[str, Any] | None = None


class WorkspaceOut(BaseModel):
    id: str
    org_id: str
    slug: str
    name: str
    description: str | None = None
    visibility: str
    archived: bool
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CollaboratorIn(BaseModel):
    user_id: str
    role: str = "viewer"
    live_control: bool = False


def _to_ws(row: Workspace) -> WorkspaceOut:
    return WorkspaceOut(
        id=row.id,
        org_id=row.org_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        visibility=row.visibility,
        archived=row.archived,
        settings=row.settings or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(
    org_id: str | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> list[WorkspaceOut]:
    stmt = select(Workspace).order_by(Workspace.name)
    if org_id:
        stmt = stmt.where(Workspace.org_id == org_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_ws(r) for r in rows]


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceIn,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(current_user),
) -> WorkspaceOut:
    row = Workspace(
        org_id=body.org_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        visibility=body.visibility,
        settings=body.settings or {},
    )
    session.add(row)
    await session.flush()
    # Auto-grant the creator as owner so the UI doesn't 403 on the next
    # request from the same user.
    session.add(
        Membership(
            user_id=user.id,
            scope_kind="workspace",
            scope_id=row.id,
            role="owner",
            live_control=True,
            granted_by=user.id,
        )
    )
    await session.commit()
    await session.refresh(row)
    return _to_ws(row)


@router.get("/{ws_id}", response_model=WorkspaceOut)
async def get_workspace(
    ws_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> WorkspaceOut:
    row = await session.get(Workspace, ws_id)
    if row is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return _to_ws(row)


@router.patch("/{ws_id}", response_model=WorkspaceOut)
async def patch_workspace(
    ws_id: str,
    body: WorkspacePatch,
    session: AsyncSession = Depends(async_session_dep),
) -> WorkspaceOut:
    row = await session.get(Workspace, ws_id)
    if row is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_ws(row)


@router.delete(
    "/{ws_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_workspace(
    ws_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    row = await session.get(Workspace, ws_id)
    if row is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    await session.delete(row)
    await session.commit()


@router.get("/{ws_id}/projects")
async def list_workspace_projects(
    ws_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Project).where(Project.workspace_id == ws_id).order_by(Project.name)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "slug": r.slug,
            "name": r.name,
            "description": r.description,
            "archived": r.archived,
        }
        for r in rows
    ]


@router.get("/{ws_id}/labs")
async def list_workspace_labs(
    ws_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Lab).where(Lab.workspace_id == ws_id).order_by(Lab.name)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "slug": r.slug,
            "name": r.name,
            "kernel_image": r.kernel_image,
            "archived": r.archived,
        }
        for r in rows
    ]


@router.get("/{ws_id}/collaborators")
async def list_collaborators(
    ws_id: str,
    session: AsyncSession = Depends(async_session_dep),
) -> list[dict[str, Any]]:
    """Lean-style ``Collaborator`` listing for a workspace."""
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.scope_kind == "workspace", Membership.scope_id == ws_id)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "uid": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "permission": m.role,
            "live_control": m.live_control,
            "owner": m.role == "owner",
        }
        for m, u in rows
    ]


@router.post("/{ws_id}/collaborators", status_code=status.HTTP_201_CREATED)
async def add_collaborator(
    ws_id: str,
    body: CollaboratorIn,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(current_user),
) -> dict[str, str]:
    if body.role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ALL_ROLES}")
    row = Membership(
        user_id=body.user_id,
        scope_kind="workspace",
        scope_id=ws_id,
        role=body.role,
        live_control=body.live_control,
        granted_by=user.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {"membership_id": row.id}
