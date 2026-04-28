"""REST endpoints for the hierarchical RAG (paper RAG#0..#3, on Redis)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


class RagCorpusInfo(BaseModel):
    name: str
    order: str
    l1: str
    l2: str
    iceberg: str | None = None
    description: str
    chunks: int = 0


class RagQueryRequest(BaseModel):
    query: str
    level: str = Field(default="l3", description="l0|l1|l2|l3")
    corpus: str | None = None
    order: str | None = Field(default=None, description="first|second|third")
    l1: str | None = None
    l2: str | None = None
    vt_symbol: str | None = None
    as_of_prefix: str | None = None
    k: int = Field(default=8, ge=1, le=50)
    rerank: bool = True
    compress: bool = True


class RagWalkRequest(BaseModel):
    query: str
    levels: list[str] = Field(default_factory=lambda: ["l0", "l1", "l2", "l3"])
    orders: list[str] = Field(default_factory=lambda: ["first", "second", "third"])
    vt_symbol: str | None = None
    as_of_prefix: str | None = None
    per_level_k: int = Field(default=5, ge=1, le=20)
    final_k: int = Field(default=8, ge=1, le=50)
    rerank: bool = True
    compress: bool = True


class RagHitDto(BaseModel):
    doc_id: str
    text: str
    score: float
    corpus: str
    level: str
    order: str
    l1: str = ""
    l2: str = ""
    vt_symbol: str = ""
    as_of: str = ""
    source_id: str = ""
    chunk_idx: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)


class RagIndexCorpusRequest(BaseModel):
    corpus: str
    kwargs: dict[str, Any] = Field(default_factory=dict)


@router.get("/corpora", response_model=list[RagCorpusInfo])
def list_corpora() -> list[RagCorpusInfo]:
    from aqp.rag import HierarchicalRAG, get_default_rag
    from aqp.rag.orders import list_corpora as _list_corpora

    try:
        rag: HierarchicalRAG = get_default_rag()
        stats = rag.stats()
    except Exception:  # pragma: no cover
        stats = {}
    return [
        RagCorpusInfo(
            name=c.name,
            order=c.order,
            l1=c.l1,
            l2=c.l2,
            iceberg=c.iceberg,
            description=c.description,
            chunks=int(stats.get(c.name, 0) or 0),
        )
        for c in _list_corpora()
    ]


@router.get("/hierarchy")
def hierarchy() -> dict[str, Any]:
    from aqp.rag.orders import KNOWLEDGE_ORDERS, l1_categories, l2_categories, list_corpora

    cats: dict[str, dict[str, list[str]]] = {}
    for l1 in l1_categories():
        cats[l1] = {l2: [] for l2 in l2_categories(l1)}
        for c in list_corpora():
            if c.l1 == l1 and c.l2 in cats[l1]:
                cats[l1][c.l2].append(c.name)
    return {"orders": list(KNOWLEDGE_ORDERS), "categories": cats}


@router.post("/query", response_model=list[RagHitDto])
def query(req: RagQueryRequest) -> list[RagHitDto]:
    from aqp.rag import get_default_rag

    try:
        hits = get_default_rag().query(
            req.query,
            level=req.level,
            corpus=req.corpus,
            order=req.order,
            l1=req.l1,
            l2=req.l2,
            vt_symbol=req.vt_symbol,
            as_of_prefix=req.as_of_prefix,
            k=req.k,
            rerank=req.rerank,
            compress=req.compress,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return [_hit_to_dto(h) for h in hits]


@router.post("/walk", response_model=list[RagHitDto])
def walk(req: RagWalkRequest) -> list[RagHitDto]:
    from aqp.rag import RAGPlan, get_default_rag

    try:
        hits = get_default_rag().walk(
            RAGPlan(
                query=req.query,
                levels=tuple(req.levels),
                orders=tuple(req.orders),
                vt_symbol=req.vt_symbol,
                as_of_prefix=req.as_of_prefix,
                per_level_k=req.per_level_k,
                final_k=req.final_k,
                rerank=req.rerank,
                compress=req.compress,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return [_hit_to_dto(h) for h in hits]


@router.post("/index/{corpus}", response_model=TaskAccepted, status_code=202)
def index_corpus(corpus: str, kwargs: dict[str, Any] | None = None) -> TaskAccepted:
    from aqp.tasks.rag_tasks import index_corpus as task

    t = task.delay(corpus, **(kwargs or {}))
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/refresh-l0", response_model=TaskAccepted, status_code=202)
def refresh_l0() -> TaskAccepted:
    from aqp.tasks.rag_tasks import refresh_l0_alpha_base

    t = refresh_l0_alpha_base.delay()
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/refresh-hierarchy", response_model=TaskAccepted, status_code=202)
def refresh_hierarchy(corpora: list[str] | None = None) -> TaskAccepted:
    from aqp.tasks.rag_tasks import refresh_hierarchy as task

    t = task.delay(corpora)
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.post("/raptor/{corpus}", response_model=TaskAccepted, status_code=202)
def raptor(
    corpus: str,
    level_target: str = "l2",
    max_levels: int = 3,
    k_max: int = 8,
    sample_size: int = 256,
) -> TaskAccepted:
    from aqp.tasks.rag_tasks import raptor_summarize

    t = raptor_summarize.delay(
        corpus,
        level_target=level_target,
        max_levels=max_levels,
        k_max=k_max,
        sample_size=sample_size,
    )
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.get("/eval")
def list_evaluations(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_rag import RagEvalRun

        with SessionLocal() as session:
            rows = (
                session.query(RagEvalRun)
                .order_by(RagEvalRun.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "level": r.level,
                    "k": r.k,
                    "n_queries": r.n_queries,
                    "aggregate": r.aggregate or {},
                    "created_at": str(r.created_at),
                }
                for r in rows
            ]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _hit_to_dto(h: Any) -> RagHitDto:
    return RagHitDto(
        doc_id=h.doc_id,
        text=h.text,
        score=float(h.score),
        corpus=h.corpus,
        level=h.level,
        order=h.order,
        l1=h.l1,
        l2=h.l2,
        vt_symbol=h.vt_symbol,
        as_of=h.as_of,
        source_id=h.source_id,
        chunk_idx=h.chunk_idx,
        meta=h.meta,
    )
