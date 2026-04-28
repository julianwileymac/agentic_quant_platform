"""Cross-encoder reranker for RAG hits.

When ``sentence-transformers`` is installed, uses ``BAAI/bge-reranker-base``
(or any model id passed via ``settings.rag_reranker``). Falls back to a
no-op that preserves the input order so callers never have to special-case
the missing dependency.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Any, Protocol

from aqp.config import settings

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, candidates: Sequence[Any]) -> list[tuple[Any, float]]:
        ...


def _doc_text(c: Any) -> str:
    return (
        getattr(c, "text", None)
        or (c.get("text") if isinstance(c, dict) else None)
        or str(c)
    )


class _CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self._encoder = CrossEncoder(model_name)
        self.name = model_name

    def rerank(self, query: str, candidates: Sequence[Any]) -> list[tuple[Any, float]]:
        if not candidates:
            return []
        pairs = [[query, _doc_text(c)] for c in candidates]
        scores = self._encoder.predict(pairs)
        scored = list(zip(candidates, scores, strict=False))
        scored.sort(key=lambda x: float(x[1]), reverse=True)
        return [(c, float(s)) for c, s in scored]


class _IdentityReranker:
    name = "identity"

    def rerank(self, query: str, candidates: Sequence[Any]) -> list[tuple[Any, float]]:
        return [(c, float(getattr(c, "score", 1.0) or 1.0)) for c in candidates]


_LOCK = threading.Lock()
_INSTANCE: Reranker | None = None


def _make_reranker() -> Reranker:
    requested = getattr(settings, "rag_reranker", "") or "BAAI/bge-reranker-base"
    try:
        return _CrossEncoderReranker(requested)
    except Exception:  # noqa: BLE001
        logger.warning(
            "Cross-encoder reranker %s unavailable; using identity reranker.",
            requested,
            exc_info=True,
        )
        return _IdentityReranker()


def get_reranker() -> Reranker:
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = _make_reranker()
    return _INSTANCE


def reset_reranker() -> None:
    global _INSTANCE
    with _LOCK:
        _INSTANCE = None


__all__ = [
    "Reranker",
    "get_reranker",
    "reset_reranker",
]
