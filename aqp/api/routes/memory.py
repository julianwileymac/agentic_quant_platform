"""REST endpoints for the agent memory layer (episodes / reflections / outcomes)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory", "agents"])


class EpisodeRow(BaseModel):
    id: str
    role: str
    vt_symbol: str | None = None
    situation: str
    lesson: str
    outcome: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class ReflectionRow(BaseModel):
    id: str
    role: str
    vt_symbol: str | None = None
    lesson: str
    outcome: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class OutcomeRow(BaseModel):
    id: str
    decision_id: str
    vt_symbol: str
    raw_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    direction_correct: float | None
    decision_at: str | None
    outcome_at: str | None


class EpisodeWriteRequest(BaseModel):
    role: str
    situation: str
    lesson: str
    outcome: float | None = None
    vt_symbol: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/episodes", response_model=list[EpisodeRow])
def list_episodes(
    role: str | None = Query(default=None),
    vt_symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[EpisodeRow]:
    from aqp.persistence.models_memory import MemoryEpisode

    with get_session() as session:
        stmt = select(MemoryEpisode)
        if role:
            stmt = stmt.where(MemoryEpisode.role == role)
        if vt_symbol:
            stmt = stmt.where(MemoryEpisode.vt_symbol == vt_symbol)
        stmt = stmt.order_by(desc(MemoryEpisode.created_at)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        EpisodeRow(
            id=r.id,
            role=r.role,
            vt_symbol=r.vt_symbol,
            situation=r.situation,
            lesson=r.lesson,
            outcome=r.outcome,
            meta=r.meta or {},
            created_at=str(r.created_at) if r.created_at else None,
        )
        for r in rows
    ]


@router.post("/episodes", response_model=EpisodeRow, status_code=201)
def write_episode(body: EpisodeWriteRequest) -> EpisodeRow:
    from aqp.llm.memory import RedisHybridMemory

    mem = RedisHybridMemory(body.role)
    eid = mem.remember_episode(
        body.situation,
        body.lesson,
        outcome=body.outcome,
        metadata={**body.metadata, "vt_symbol": body.vt_symbol or ""},
    )
    return EpisodeRow(
        id=eid,
        role=body.role,
        vt_symbol=body.vt_symbol,
        situation=body.situation,
        lesson=body.lesson,
        outcome=body.outcome,
        meta=body.metadata,
    )


@router.get("/reflections", response_model=list[ReflectionRow])
def list_reflections(
    role: str | None = Query(default=None),
    vt_symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[ReflectionRow]:
    from aqp.persistence.models_memory import MemoryReflection

    with get_session() as session:
        stmt = select(MemoryReflection)
        if role:
            stmt = stmt.where(MemoryReflection.role == role)
        if vt_symbol:
            stmt = stmt.where(MemoryReflection.vt_symbol == vt_symbol)
        stmt = stmt.order_by(desc(MemoryReflection.created_at)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        ReflectionRow(
            id=r.id,
            role=r.role,
            vt_symbol=r.vt_symbol,
            lesson=r.lesson,
            outcome=r.outcome,
            meta=r.meta or {},
            created_at=str(r.created_at) if r.created_at else None,
        )
        for r in rows
    ]


@router.get("/outcomes", response_model=list[OutcomeRow])
def list_outcomes(
    vt_symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[OutcomeRow]:
    from aqp.persistence.models_memory import MemoryOutcome

    with get_session() as session:
        stmt = select(MemoryOutcome)
        if vt_symbol:
            stmt = stmt.where(MemoryOutcome.vt_symbol == vt_symbol)
        stmt = stmt.order_by(desc(MemoryOutcome.created_at)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        OutcomeRow(
            id=r.id,
            decision_id=r.decision_id,
            vt_symbol=r.vt_symbol,
            raw_return=r.raw_return,
            benchmark_return=r.benchmark_return,
            excess_return=r.excess_return,
            direction_correct=r.direction_correct,
            decision_at=str(r.decision_at) if r.decision_at else None,
            outcome_at=str(r.outcome_at) if r.outcome_at else None,
        )
        for r in rows
    ]


@router.post("/reflect/run")
def run_reflection_pass(body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """Trigger a synchronous reflection pass (Celery wrapper exists too)."""
    from aqp.agents.analysis.reflector import run_reflection_pass as _run

    return _run(**body)


@router.delete(
    "/episodes/{episode_id}",
    status_code=204,
    response_class=Response,
)
def delete_episode(episode_id: str) -> Response:
    from aqp.persistence.models_memory import MemoryEpisode

    with get_session() as session:
        row = session.get(MemoryEpisode, episode_id)
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        session.delete(row)
        session.commit()
    return Response(status_code=204)
