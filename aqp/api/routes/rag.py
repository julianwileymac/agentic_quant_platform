"""REST endpoints for the hierarchical RAG (paper RAG#0..#3, on Redis).

Also hosts the math-aware research-paper sub-surface under
``/rag/papers/*`` introduced for the 2026 research-report consolidation:

- ``POST /rag/papers/upload`` — multipart PDF upload + queue ingest task
- ``GET  /rag/papers`` — paginated paper list with filters
- ``GET  /rag/papers/{id}`` — paper detail (metadata + first chunks)
- ``POST /rag/papers/{id}/synthesize`` — LLM-drafted YAML strategy
- ``POST /rag/papers/query-hybrid`` — dense+sparse RRF retrieval
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
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


# ---------------------------------------------------------------------------
# Research-paper RAG sub-surface
# ---------------------------------------------------------------------------


class ResearchPaperRowDto(BaseModel):
    id: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    author_institution: str | None = None
    publication_year: int | None = None
    asset_class: list[str] = Field(default_factory=list)
    strategy_family: str | None = None
    contains_mathematics: bool | None = None
    equation_count: int | None = None
    chunk_count: int | None = None
    parser_used: str | None = None
    abstract: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


def _paper_to_dto(row: Any) -> ResearchPaperRowDto:
    return ResearchPaperRowDto(
        id=str(row.id),
        title=row.title,
        authors=list(row.authors or []),
        author_institution=row.author_institution,
        publication_year=row.publication_year,
        asset_class=list(row.asset_class or []),
        strategy_family=row.strategy_family,
        contains_mathematics=row.contains_mathematics,
        equation_count=row.equation_count or 0,
        chunk_count=row.chunk_count or 0,
        parser_used=row.parser_used,
        abstract=row.abstract,
        meta=dict(row.meta or {}),
        created_at=str(row.created_at) if row.created_at else None,
    )


@router.post("/papers/upload", response_model=TaskAccepted, status_code=202)
async def upload_research_paper(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    authors: str | None = Form(default=None),
    author_institution: str | None = Form(default=None),
    publication_year: int | None = Form(default=None),
    asset_class: str | None = Form(default=None),
    strategy_family: str | None = Form(default=None),
) -> TaskAccepted:
    """Upload a research PDF and queue async ingestion.

    The PDF is saved into ``settings.rag_paper_root``. A new
    ``research_papers`` row is created with the supplied metadata
    *before* the ingest task is queued so the frontend can
    immediately deep-link to the paper detail page.
    """
    from aqp.config import settings
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_research_papers import ResearchPaperRow
    from aqp.tasks.research_paper_tasks import ingest_research_paper

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > settings.rag_paper_max_mb:
        raise HTTPException(
            status_code=413,
            detail=f"upload too large: {size_mb:.1f} MB > {settings.rag_paper_max_mb} MB cap",
        )

    paper_root = Path(settings.rag_paper_root)
    paper_root.mkdir(parents=True, exist_ok=True)
    target = paper_root / f"{os.urandom(8).hex()}_{file.filename}"
    target.write_bytes(raw)

    with SessionLocal() as session:
        row = ResearchPaperRow(
            title=title,
            authors=[a.strip() for a in (authors or "").split(",") if a.strip()],
            author_institution=author_institution,
            publication_year=publication_year,
            asset_class=[a.strip() for a in (asset_class or "").split(",") if a.strip()],
            strategy_family=strategy_family,
            pdf_path=str(target),
            meta={"original_filename": file.filename or ""},
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        paper_id = str(row.id)
    t = ingest_research_paper.delay(paper_id=paper_id)
    return TaskAccepted(task_id=t.id, stream_url=f"/ws/progress/{t.id}")


@router.get("/papers", response_model=list[ResearchPaperRowDto])
def list_research_papers(
    strategy_family: str | None = None,
    contains_mathematics: bool | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[ResearchPaperRowDto]:
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_research_papers import ResearchPaperRow

    with SessionLocal() as session:
        qry = session.query(ResearchPaperRow).order_by(
            ResearchPaperRow.created_at.desc()
        )
        if strategy_family:
            qry = qry.filter(ResearchPaperRow.strategy_family == strategy_family)
        if contains_mathematics is not None:
            qry = qry.filter(ResearchPaperRow.contains_mathematics == contains_mathematics)
        if q:
            ql = f"%{q.lower()}%"
            qry = qry.filter(
                (ResearchPaperRow.title.ilike(ql))
                | (ResearchPaperRow.abstract.ilike(ql))
            )
        return [_paper_to_dto(r) for r in qry.limit(limit).all()]


@router.get("/papers/{paper_id}")
def get_research_paper(paper_id: str) -> dict[str, Any]:
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_research_papers import ResearchPaperRow
    from aqp.rag import get_default_rag

    with SessionLocal() as session:
        row = session.query(ResearchPaperRow).filter_by(id=paper_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="paper not found")
        dto = _paper_to_dto(row).model_dump()
    # Pull a small preview of chunks from the RAG store.
    chunks: list[dict[str, Any]] = []
    try:
        rag = get_default_rag()
        hits = rag.query(
            query=row.title or "",
            corpus="research_papers",
            level="l2",
            k=10,
            rerank=False,
            compress=False,
        )
        for h in hits:
            chunks.append(
                {
                    "chunk_id": h.doc_id,
                    "text": h.text,
                    "contains_mathematics": "$" in (h.text or "")
                    or "\\(" in (h.text or "")
                    or "\\[" in (h.text or ""),
                    "section": h.meta.get("section") if isinstance(h.meta, dict) else None,
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper chunk preview failed: %s", exc)
    dto["chunks"] = chunks
    return dto


class PaperSynthesizeResp(BaseModel):
    yaml: str
    rationale: str | None = None


@router.post("/papers/{paper_id}/synthesize", response_model=PaperSynthesizeResp)
def synthesize_strategy_from_paper_route(paper_id: str) -> PaperSynthesizeResp:
    from aqp.tasks.research_paper_tasks import synthesize_strategy_impl

    result = synthesize_strategy_impl(paper_id=paper_id)
    return PaperSynthesizeResp(yaml=result["yaml"], rationale=result.get("rationale"))


class PaperHybridQuery(BaseModel):
    query: str
    k: int = 10
    dense_weight: float = 1.0
    sparse_weight: float = 1.0


@router.post("/papers/query-hybrid", response_model=list[RagHitDto])
def query_research_papers_hybrid(req: PaperHybridQuery) -> list[RagHitDto]:
    from aqp.rag import get_default_rag

    try:
        hits = get_default_rag().query_hybrid(
            query=req.query,
            corpus="research_papers",
            level="l2",
            k=req.k,
            dense_weight=req.dense_weight,
            sparse_weight=req.sparse_weight,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return [_hit_to_dto(h) for h in hits]


# Suppress unused-import lint when this surface ships before its
# dependencies (e.g. shutil for ingest tasks).
_ = shutil


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
