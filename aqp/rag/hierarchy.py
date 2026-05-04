"""Top-level HierarchicalRAG facade (Alpha-GPT levels + AQP orders).

The facade abstracts the four-level hierarchy described in the paper:

- ``query(level=...)`` — direct retrieval at one level.
- ``walk(query)`` — top-down navigation L0 → L1 → L2 → L3 mirroring
  paper Section 3.2 (autonomous mode).
- ``index_chunk`` / ``index_chunks`` — write a leaf chunk to a corpus.
- ``index_summary`` — write an internal RAPTOR-style summary node at L1
  or L2.
- ``precompute_l0_alpha_base`` — bulk-index the past
  decision/equity-report/backtest base (paper RAG#0).
- ``recall_for_prompt`` — convenience that returns a context block
  ready to splice into a system or user prompt.

All retrievals are written to ``rag_queries`` for audit (when the table
exists). All writes pass through the per-corpus indexers under
:mod:`aqp.rag.indexers` so adding a new source is a single subclass.
"""
from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from aqp.config import settings
from aqp.rag.chunker import Chunk
from aqp.rag.compressor import compress_text, filter_candidates
from aqp.rag.embedder import Embedder, get_embedder
from aqp.rag.orders import (
    KnowledgeOrder,
    OrderCorpus,
    get_corpus,
    list_corpora,
)
from aqp.rag.redis_store import RedisVectorStore, VectorHit, VectorRecord
from aqp.rag.reranker import get_reranker

logger = logging.getLogger(__name__)


@dataclass
class RAGHit:
    """One retrieval result returned to callers."""

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
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_vector(cls, hit: VectorHit) -> "RAGHit":
        return cls(
            doc_id=hit.doc_id,
            text=hit.text,
            score=hit.score,
            corpus=hit.corpus,
            level=hit.level,
            order=hit.order,
            l1=hit.l1,
            l2=hit.l2,
            vt_symbol=hit.vt_symbol,
            as_of=hit.as_of,
            source_id=hit.source_id,
            chunk_idx=hit.chunk_idx,
            meta=dict(hit.meta or {}),
        )


@dataclass
class RAGPlan:
    """A query plan over the hierarchy.

    Mirrors the paper's autonomous-mode top-down walk. ``levels`` lists
    the levels to query; ``orders`` constrains to a subset of knowledge
    tiers; ``per_level_k`` controls fan-out at each hop.
    """

    query: str
    levels: tuple[str, ...] = ("l0", "l1", "l2", "l3")
    orders: tuple[KnowledgeOrder, ...] = ("first", "second", "third")
    per_level_k: int = 5
    final_k: int = 8
    vt_symbol: str | None = None
    as_of_prefix: str | None = None
    rerank: bool = True
    compress: bool = True


class HierarchicalRAG:
    """Top-level RAG entry point.

    Owns one :class:`RedisVectorStore` and one :class:`Embedder`. Use
    :func:`get_default_rag` for the process-wide cached singleton.
    """

    def __init__(
        self,
        *,
        store: RedisVectorStore | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.embedder = embedder or get_embedder()
        self.store = store or RedisVectorStore(embed_dim=self.embedder.dim)

    # ------------------------------------------------------------------ writes
    def index_chunks(
        self,
        corpus_name: str,
        records: Iterable[tuple[Chunk, dict[str, Any]]],
        *,
        level: str = "l3",
    ) -> int:
        """Index ``(chunk, metadata)`` pairs into the given corpus / level."""
        corpus = get_corpus(corpus_name)
        records = list(records)
        if not records:
            return 0
        texts = [chunk.text for chunk, _ in records]
        vectors = self.embedder.embed(texts)
        out: list[tuple[VectorRecord, list[float]]] = []
        for (chunk, meta), vec in zip(records, vectors, strict=False):
            doc_id = str(meta.get("doc_id") or uuid.uuid4())
            rec = VectorRecord(
                doc_id=doc_id,
                text=chunk.text,
                corpus=corpus.name,
                level=level,
                order=corpus.order,
                l1=corpus.l1,
                l2=corpus.l2,
                vt_symbol=str(meta.get("vt_symbol", "") or ""),
                as_of=str(meta.get("as_of", "") or ""),
                source_id=str(meta.get("source_id", "") or ""),
                chunk_idx=int(chunk.index),
                meta={
                    k: v
                    for k, v in meta.items()
                    if k not in {"doc_id", "vt_symbol", "as_of", "source_id"}
                },
            )
            out.append((rec, vec))
        return self.store.upsert(out)

    def index_summary(
        self,
        corpus_name: str,
        *,
        level: str,
        text: str,
        member_ids: Sequence[str],
        vt_symbol: str | None = None,
        as_of: str | None = None,
        source_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """Write a single summary node (used by RAPTOR + L0 base)."""
        if level not in {"l0", "l1", "l2"}:
            raise ValueError(f"summary level must be l0/l1/l2, got {level!r}")
        corpus = get_corpus(corpus_name)
        doc_id = str(uuid.uuid4())
        vec = self.embedder.embed_one(text)
        rec = VectorRecord(
            doc_id=doc_id,
            text=text,
            corpus=corpus.name,
            level=level,
            order=corpus.order,
            l1=corpus.l1,
            l2=corpus.l2 if level == "l2" else "",
            vt_symbol=vt_symbol or "",
            as_of=as_of or "",
            source_id=source_id or "",
            chunk_idx=0,
            meta={"member_ids": list(member_ids), **(meta or {})},
        )
        self.store.upsert([(rec, vec)])
        return doc_id

    # ------------------------------------------------------------------ reads
    def query(
        self,
        query: str,
        *,
        level: str = "l3",
        corpus: str | None = None,
        order: KnowledgeOrder | None = None,
        l1: str | None = None,
        l2: str | None = None,
        vt_symbol: str | None = None,
        as_of_prefix: str | None = None,
        k: int = 8,
        rerank: bool = True,
        compress: bool = True,
        compress_threshold: float = 0.15,
        context: Any | None = None,
    ) -> list[RAGHit]:
        """Direct vector search at one level, with optional rerank."""
        qvec = self.embedder.embed_one(query)
        searched: list[VectorHit] = []
        if corpus:
            searched = self.store.search(
                qvec,
                k=k * 3 if rerank else k,
                corpus=corpus,
                level=level,
                order=order,
                l1=l1,
                l2=l2,
                vt_symbol=vt_symbol,
                as_of_prefix=as_of_prefix,
            )
        else:
            for c in list_corpora():
                if order and c.order != order:
                    continue
                if l1 and c.l1 != l1:
                    continue
                if l2 and c.l2 != l2:
                    continue
                searched.extend(
                    self.store.search(
                        qvec,
                        k=k * 2,
                        corpus=c.name,
                        level=level,
                        order=order,
                        l1=l1,
                        l2=l2,
                        vt_symbol=vt_symbol,
                        as_of_prefix=as_of_prefix,
                    )
                )
        if compress and searched:
            searched = filter_candidates(query, searched, threshold=compress_threshold) or searched
        if rerank and searched:
            ranked = get_reranker().rerank(query, searched)
            searched = [h for h, _ in ranked]
        hits = [RAGHit.from_vector(h) for h in searched[:k]]
        hits = self._filter_for_context(hits, context)
        self._audit(query, hits, plan_level=level, plan_corpus=corpus or "", context=context)
        return hits

    def walk(self, plan: RAGPlan, *, context: Any | None = None) -> list[RAGHit]:
        """Top-down navigation L0 → L1 → L2 → L3 (paper Section 3.2).

        At each level we pick the highest-scoring few hits, narrow the
        ``(l1, l2)`` filter to follow them, and drill into the next.
        """
        qvec = self.embedder.embed_one(plan.query)
        breadth_l1: set[str] = set()
        breadth_l2: set[str] = set()
        all_hits: list[RAGHit] = []

        for level in plan.levels:
            level_hits: list[VectorHit] = []
            for corpus in list_corpora():
                if corpus.order not in plan.orders:
                    continue
                if level == "l2" and breadth_l1 and corpus.l1 not in breadth_l1:
                    continue
                if level == "l3" and breadth_l2 and corpus.l2 not in breadth_l2:
                    continue
                level_hits.extend(
                    self.store.search(
                        qvec,
                        k=plan.per_level_k,
                        corpus=corpus.name,
                        level=level,
                        vt_symbol=plan.vt_symbol,
                        as_of_prefix=plan.as_of_prefix,
                    )
                )
            level_hits.sort(key=lambda h: h.score, reverse=True)
            top = level_hits[: plan.per_level_k]
            for h in top:
                if h.l1:
                    breadth_l1.add(h.l1)
                if h.l2:
                    breadth_l2.add(h.l2)
            all_hits.extend(RAGHit.from_vector(h) for h in top)

        if plan.rerank and all_hits:
            ranked = get_reranker().rerank(plan.query, all_hits)
            all_hits = [h for h, _ in ranked]
        if plan.compress and all_hits:
            all_hits = filter_candidates(plan.query, all_hits, threshold=0.12) or all_hits
        out = all_hits[: plan.final_k]
        out = self._filter_for_context(out, context)
        self._audit(plan.query, out, plan_level="walk", plan_corpus="*", context=context)
        return out

    def recall_for_prompt(
        self,
        query: str,
        *,
        plan: RAGPlan | None = None,
        max_tokens: int = 1500,
        header: str = "## Retrieved context",
    ) -> str:
        """Return a markdown context block ready for prompt injection."""
        plan = plan or RAGPlan(query=query)
        hits = self.walk(plan)
        if not hits:
            return ""
        lines: list[str] = [header]
        for i, h in enumerate(hits, 1):
            label = f"[{h.corpus}/{h.level}]"
            if h.vt_symbol:
                label += f" {h.vt_symbol}"
            if h.as_of:
                label += f" {h.as_of}"
            lines.append(f"{i}. {label} (score={h.score:.3f})")
            lines.append(compress_text(h.text, max_tokens=max_tokens // max(1, len(hits))))
        return "\n".join(lines)

    # ------------------------------------------------------------------ helpers
    def precompute_l0_alpha_base(
        self,
        decisions: Iterable[dict[str, Any]],
    ) -> int:
        """Index the alpha/decision base used by paper RAG#0.

        Each input dict is expected to carry at least ``id``, ``text``
        (rendered narrative of the decision + outcome), ``vt_symbol``,
        ``as_of``, plus arbitrary extra metadata.
        """
        records: list[tuple[Chunk, dict[str, Any]]] = []
        for d in decisions:
            text = (d.get("text") or "").strip()
            if not text:
                continue
            chunk = Chunk(text=text, index=0, token_count=len(text.split()))
            meta = {
                "doc_id": str(d.get("id") or uuid.uuid4()),
                "vt_symbol": d.get("vt_symbol", "") or "",
                "as_of": d.get("as_of", "") or "",
                "source_id": d.get("source_id", "") or d.get("id", ""),
                **{k: v for k, v in d.items() if k not in {"id", "text", "vt_symbol", "as_of", "source_id"}},
            }
            records.append((chunk, meta))
        return self.index_chunks("decisions", records, level="l0")

    def delete_corpus(self, corpus_name: str) -> int:
        """Drop every chunk for a corpus across all levels."""
        return self.store.delete_corpus(corpus_name)

    def stats(self) -> dict[str, int]:
        """Per-corpus chunk counts (across all levels)."""
        out: dict[str, int] = {}
        for c in list_corpora():
            out[c.name] = self.store.count(corpus=c.name)
        return out

    # ------------------------------------------------------------------ tenancy
    def _filter_for_context(
        self, hits: list[RAGHit], context: Any | None
    ) -> list[RAGHit]:
        """Filter hits to corpora the user can see.

        With the current data model every RAG corpus row stores
        ``owner_user_id`` / ``workspace_id`` / ``lab_id``. We look up the
        rows for the corpora referenced in *hits* and keep only those
        whose lab is in the user's accessible-labs set (or whose
        workspace is accessible). When *context* is the local-first
        default — or no context is supplied — we return hits unchanged
        so existing single-tenant flows keep working.
        """
        if context is None or getattr(context, "user_id", None) in (None, "00000000-0000-0000-0000-000000000003"):
            return hits
        try:
            corpus_names = {h.corpus for h in hits}
            if not corpus_names:
                return hits
            from aqp.auth.user import accessible_labs, accessible_workspaces, resolve_user
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_rag import RagCorpus

            user = resolve_user(user_id=context.user_id)
            allowed_workspaces = set(accessible_workspaces(user))
            allowed_labs = set(accessible_labs(user))
            with SessionLocal() as session:
                rows = (
                    session.query(
                        RagCorpus.name,
                        RagCorpus.workspace_id,
                        RagCorpus.lab_id,
                    )
                    .filter(RagCorpus.name.in_(corpus_names))
                    .all()
                )
                visible: set[str] = set()
                for name, ws, lab in rows:
                    # No tenancy stamp = legacy default-bucket = visible to everyone.
                    if not ws and not lab:
                        visible.add(name)
                    elif ws in allowed_workspaces or lab in allowed_labs:
                        visible.add(name)
                # Corpora not present in the table (cache miss / fresh corpus)
                # default to visible — denial-by-omission would silently
                # drop legitimate results.
                visible.update(corpus_names - {r[0] for r in rows})
            return [h for h in hits if h.corpus in visible]
        except Exception:
            logger.debug("RAG workspace filter skipped", exc_info=True)
            return hits

    # ------------------------------------------------------------------ audit
    def _audit(
        self,
        query: str,
        hits: Sequence[RAGHit],
        *,
        plan_level: str,
        plan_corpus: str,
        context: Any | None = None,
    ) -> None:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_rag import RagQuery
        except Exception:  # pragma: no cover
            return
        if not getattr(settings, "rag_audit_enabled", True):
            return
        try:
            payload = [
                {
                    "doc_id": h.doc_id,
                    "score": float(h.score),
                    "corpus": h.corpus,
                    "level": h.level,
                    "vt_symbol": h.vt_symbol,
                    "as_of": h.as_of,
                }
                for h in hits
            ]
            row = RagQuery(
                query=query[:8000],
                plan_level=plan_level,
                plan_corpus=plan_corpus,
                results=payload,
                result_count=len(hits),
            )
            if context is not None:
                if getattr(context, "user_id", None):
                    row.owner_user_id = context.user_id
                if getattr(context, "workspace_id", None):
                    row.workspace_id = context.workspace_id
                if getattr(context, "lab_id", None):
                    row.lab_id = context.lab_id
            with SessionLocal() as session:
                session.add(row)
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("RAG audit log skipped (table likely not yet migrated).", exc_info=True)


_LOCK = threading.Lock()
_INSTANCE: HierarchicalRAG | None = None


def get_default_rag() -> HierarchicalRAG:
    """Return the process-wide cached :class:`HierarchicalRAG`."""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = HierarchicalRAG()
    return _INSTANCE


def reset_default_rag() -> None:
    """Reset the cached singleton (used by tests)."""
    global _INSTANCE
    with _LOCK:
        _INSTANCE = None


__all__ = [
    "HierarchicalRAG",
    "RAGHit",
    "RAGPlan",
    "get_default_rag",
    "reset_default_rag",
]
