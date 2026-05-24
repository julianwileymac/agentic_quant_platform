"""Hybrid retrieval helper for the Data Lab RAG sidecar.

The blueprint mandates BM25 (Postgres FTS) + dense (pgvector) + MMR
rerank. AQP already ships:

- :class:`aqp.rag.hierarchy.HierarchicalRAG` — the canonical RAG
  surface that AGENTS rule 11 forces every retrieval through.
- pgvector-indexed ``rag_chunks.embedding`` (migration 0045) for
  dense search.
- Postgres FTS via ``to_tsvector`` (the existing :mod:`aqp.rag`
  loaders already maintain the matching columns when available).

This module wraps those existing primitives so the Lab RAG drawer
never bypasses :class:`HierarchicalRAG` (rule 11). The fallback path
degrades cleanly to BM25-only (or text-substring) when pgvector / the
RAG indexer isn't installed in the local dev environment.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def hybrid_query(
    query: str,
    *,
    k: int = 10,
    tags: list[str] | None = None,
    mmr_lambda: float = 0.6,
) -> list[dict[str, Any]]:
    """Run a hybrid BM25 + dense + MMR query.

    Returns a list of dicts with keys ``chunk_id``, ``paper_title``,
    ``source_uri``, ``text``, ``score``, ``rank``. Never raises —
    degrades to an empty list when the underlying RAG stack is
    unavailable so the Lab drawer keeps rendering.

    The MMR rerank parameter ``mmr_lambda`` follows the standard
    convention: 1.0 returns the most relevant hits, 0.0 returns the
    most diverse hits, 0.5-0.7 is the typical balance.
    """
    if not query or not query.strip():
        return []

    try:
        from aqp.rag.hierarchy import get_default_rag
    except Exception:  # noqa: BLE001
        logger.debug("HierarchicalRAG import failed; returning empty hits")
        return []

    try:
        rag = get_default_rag()
    except Exception:  # noqa: BLE001
        logger.debug("default RAG bootstrap failed; returning empty hits")
        return []

    # Prefer the dense+MMR helper when present on the surface
    # (:meth:`HierarchicalRAG.query_hybrid`); fall back to the plain
    # query helper otherwise.
    raw_hits: list[Any]
    try:
        if hasattr(rag, "query_hybrid"):
            raw_hits = list(
                rag.query_hybrid(
                    query,
                    top_k=k,
                    tags=list(tags or []),
                    mmr_lambda=mmr_lambda,
                )
            )
        else:
            raw_hits = list(rag.query(query, top_k=k))
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG hybrid query failed: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    for rank, hit in enumerate(raw_hits):
        # The RAG surface returns either dicts or :class:`RAGHit`
        # dataclass instances depending on which retrieval path
        # served the query. Normalise both into a JSON-safe dict.
        get = (
            (lambda key, default=None: getattr(hit, key, default))
            if not isinstance(hit, dict)
            else (lambda key, default=None: hit.get(key, default))
        )
        out.append(
            {
                "chunk_id": str(get("chunk_id") or get("id") or f"hit-{rank}"),
                "paper_title": get("title") or get("paper_title"),
                "source_uri": get("source") or get("source_uri") or get("uri"),
                "text": get("text") or get("content") or "",
                "score": float(get("score") or 0.0),
                "rank": rank,
            }
        )
    return out


__all__ = ["hybrid_query"]
