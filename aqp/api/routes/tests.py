"""``/tests`` — Phase 1 assertion CRUD attached to experiments.

A ``Test`` is the rubric an experiment is graded against, not the typed
run itself. Multiple tests can attach to one experiment (e.g. Sharpe
> 1, max DD < 10%, trades > 50) and the typed runs reference the same
experiment via ``experiment_id``.
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
from aqp.persistence.models_experiments import (
    Experiment,
    TEST_KINDS,
    Test,
)

router = APIRouter(prefix="/tests", tags=["tests"])


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower().strip()).strip("-")
    return base[:120] or "test"


class TestIn(BaseModel):
    experiment_id: str
    name: str
    slug: str | None = None
    description: str | None = None
    assertion_kind: str = "metric_threshold"
    details: dict[str, Any] = Field(default_factory=dict)


class TestEvaluation(BaseModel):
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)
    run_ref_table: str | None = None
    run_ref_id: str | None = None


class TestOut(BaseModel):
    id: str
    experiment_id: str
    slug: str
    name: str
    description: str | None = None
    assertion_kind: str
    passed: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    run_ref_table: str | None = None
    run_ref_id: str | None = None
    evaluated_at: datetime | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    owner_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


def _to_out(row: Test) -> TestOut:
    return TestOut(
        id=row.id,
        experiment_id=row.experiment_id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        assertion_kind=row.assertion_kind,
        passed=row.passed,
        details=dict(row.details or {}),
        run_ref_table=row.run_ref_table,
        run_ref_id=row.run_ref_id,
        evaluated_at=row.evaluated_at,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        owner_user_id=row.owner_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[TestOut])
async def list_tests(
    experiment_id: str | None = None,
    passed: bool | None = None,
    limit: int = 200,
    session: AsyncSession = Depends(async_session_dep),
    ctx: RequestContext = Depends(current_context),
    _: CurrentUser = Depends(require_authenticated),
) -> list[TestOut]:
    stmt = select(Test).order_by(Test.updated_at.desc()).limit(limit)
    if experiment_id:
        stmt = stmt.where(Test.experiment_id == experiment_id)
    elif ctx.project_id:
        stmt = stmt.where(Test.project_id == ctx.project_id)
    if passed is not None:
        stmt = stmt.where(Test.passed.is_(passed))
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=TestOut, status_code=status.HTTP_201_CREATED)
async def create_test(
    body: TestIn,
    session: AsyncSession = Depends(async_session_dep),
    user: CurrentUser = Depends(require_authenticated),
) -> TestOut:
    if body.assertion_kind not in TEST_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"assertion_kind must be one of {TEST_KINDS}",
        )
    parent = await session.get(Experiment, body.experiment_id)
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="parent experiment not found"
        )
    row = Test(
        experiment_id=body.experiment_id,
        slug=body.slug or _slugify(body.name),
        name=body.name,
        description=body.description,
        assertion_kind=body.assertion_kind,
        details=dict(body.details or {}),
        owner_user_id=user.id,
        workspace_id=parent.workspace_id,
        project_id=parent.project_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.get("/{test_id}", response_model=TestOut)
async def get_test(
    test_id: str,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> TestOut:
    row = await session.get(Test, test_id)
    if row is None:
        raise HTTPException(status_code=404, detail="test not found")
    return _to_out(row)


@router.post("/{test_id}/evaluate", response_model=TestOut)
async def evaluate_test(
    test_id: str,
    body: TestEvaluation,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> TestOut:
    row = await session.get(Test, test_id)
    if row is None:
        raise HTTPException(status_code=404, detail="test not found")
    row.passed = bool(body.passed)
    row.details = dict(body.details or row.details or {})
    row.run_ref_table = body.run_ref_table
    row.run_ref_id = body.run_ref_id
    row.evaluated_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_out(row)


@router.delete(
    "/{test_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_test(
    test_id: str,
    session: AsyncSession = Depends(async_session_dep),
    _: CurrentUser = Depends(require_authenticated),
) -> None:
    row = await session.get(Test, test_id)
    if row is None:
        raise HTTPException(status_code=404, detail="test not found")
    await session.delete(row)
    await session.commit()


__all__ = ["TestEvaluation", "TestIn", "TestOut", "router"]
