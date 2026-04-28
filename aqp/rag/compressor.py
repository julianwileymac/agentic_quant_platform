"""Embeddings-filter contextual compression.

Implements LangChain's ``EmbeddingsFilter`` pattern (used by FinGPT
``MultiAgentsRAG``) without the LangChain dependency: drops candidates
whose cosine similarity to the query falls below a threshold.

Use this as a cheap second-stage between the vector store and the
cross-encoder reranker, or as the only filter when the reranker model
isn't installed.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from aqp.rag.embedder import get_embedder

logger = logging.getLogger(__name__)


def _doc_text(c: Any) -> str:
    return (
        getattr(c, "text", None)
        or (c.get("text") if isinstance(c, dict) else None)
        or str(c)
    )


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    s = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        s += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return s / ((na**0.5) * (nb**0.5))


def filter_candidates(
    query: str,
    candidates: Sequence[Any],
    *,
    threshold: float = 0.18,
    max_keep: int | None = None,
) -> list[Any]:
    """Return only candidates above ``threshold`` cosine sim to ``query``."""
    if not candidates:
        return []
    embedder = get_embedder()
    qvec = embedder.embed_one(query)
    docs = [_doc_text(c) for c in candidates]
    dvecs = embedder.embed(docs)
    keep: list[tuple[Any, float]] = []
    for cand, vec in zip(candidates, dvecs, strict=False):
        sim = _cosine(qvec, vec)
        if sim >= threshold:
            keep.append((cand, sim))
    keep.sort(key=lambda x: x[1], reverse=True)
    if max_keep is not None:
        keep = keep[:max_keep]
    return [c for c, _ in keep]


def compress_text(text: str, *, max_tokens: int = 800) -> str:
    """Crude token-budget cap for downstream prompts.

    Used to keep retrieved context within the model's context window
    without truncating mid-word.
    """
    if not text:
        return ""
    words = text.split()
    if len(words) <= max_tokens:
        return text
    return " ".join(words[:max_tokens]) + " ..."


__all__ = ["compress_text", "filter_candidates"]
