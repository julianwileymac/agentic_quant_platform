"""Embedding model abstraction.

Default: ``BAAI/bge-m3`` via ``sentence-transformers`` (matches the paper).
Falls back to ``all-MiniLM-L6-v2`` if BGE-M3 is unavailable, and finally
to a deterministic hash-based vector so unit tests run hermetically.

The embedder is process-cached and thread-safe; call :func:`get_embedder`
to retrieve the singleton.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Iterable
from typing import Protocol

from aqp.config import settings

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Interface every concrete embedder satisfies."""

    name: str
    dim: int

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        """Return one float vector per input text."""
        ...

    def embed_one(self, text: str) -> list[float]:
        """Embed a single text. Convenience over :meth:`embed`."""
        ...


class _SentenceTransformerEmbedder:
    """Sentence-Transformers backed embedder."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.name = model_name
        try:
            self.dim = int(self._model.get_sentence_embedding_dimension())
        except Exception:  # pragma: no cover - older versions
            self.dim = len(self._model.encode(["probe"], show_progress_bar=False)[0])

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        items = [t or "" for t in texts]
        if not items:
            return []
        vecs = self._model.encode(
            items,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [list(map(float, v)) for v in vecs]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class _HashEmbedder:
    """Deterministic, dependency-free fallback for tests / cold installs.

    Maps each token to a small bag-of-features vector via SHA-256 mod
    :attr:`dim`. Quality is poor but stable and zero-cost.
    """

    def __init__(self, dim: int = 384) -> None:
        self.name = f"hash-{dim}"
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        out = [0.0] * self.dim
        for tok in (text or "").lower().split():
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if (h[4] & 1) == 0 else -1.0
            out[idx] += sign
        norm = sum(v * v for v in out) ** 0.5
        if norm > 0:
            out = [v / norm for v in out]
        return out

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        return self._vec(text)


_LOCK = threading.Lock()
_INSTANCE: Embedder | None = None


def _make_embedder() -> Embedder:
    requested = getattr(settings, "rag_embedder", "") or "BAAI/bge-m3"
    candidates: list[str] = [requested]
    if requested != "all-MiniLM-L6-v2":
        candidates.append("all-MiniLM-L6-v2")
    for model_name in candidates:
        try:
            return _SentenceTransformerEmbedder(model_name)
        except Exception:  # noqa: BLE001
            logger.debug("Embedder %s unavailable; trying next.", model_name, exc_info=True)
    logger.warning(
        "No sentence-transformers model available; falling back to deterministic hash embedder."
    )
    return _HashEmbedder()


def get_embedder() -> Embedder:
    """Return the process-wide cached :class:`Embedder` instance."""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = _make_embedder()
    return _INSTANCE


def reset_embedder() -> None:
    """Drop the cached embedder. Used by tests after monkey-patching settings."""
    global _INSTANCE
    with _LOCK:
        _INSTANCE = None


__all__ = [
    "Embedder",
    "get_embedder",
    "reset_embedder",
]
