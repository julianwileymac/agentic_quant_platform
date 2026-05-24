"""Data Lab RAG sidecar — hybrid query over RagChunks + pgvector.

Wraps :class:`aqp.rag.hierarchy.HierarchicalRAG` so the operator's
right-rail drawer can run BM25 + dense + MMR-reranked queries against
the same paper corpus the rest of AQP uses. Adding a paper goes
through the existing :mod:`aqp.rag` pipeline + the upstream
``/labs/{lab_id}/corpora`` route on
:mod:`aqp.api.routes.labs` — we don't fork the canonical surface.
"""
from __future__ import annotations

from aqp.lab.rag.hybrid_query import hybrid_query

__all__ = ["hybrid_query"]
