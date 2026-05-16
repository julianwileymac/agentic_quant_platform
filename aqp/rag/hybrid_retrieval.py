"""Reciprocal Rank Fusion of dense + sparse RAG hits.

The :class:`HierarchicalRAG` default retrieval path is dense KNN over
BGE-M3 embeddings. For the math-heavy research-paper corpus, exact
token matches (variable names, ticker codes, theorem numbers) are
just as important as semantic similarity. We expose a hybrid path
that fuses two ranked lists via Reciprocal Rank Fusion (Cormack
2009):

.. math::

    \\mathrm{score}_{RRF}(d) = \\sum_{r \\in \\{dense, sparse\\}}
        \\frac{1}{k + \\mathrm{rank}_r(d)}.

The fusion is corpus-aware (you can choose dense-only / sparse-only
per corpus) and falls back gracefully when sparse search isn't
available (e.g. RediSearch missing in dev mode).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from aqp.rag.redis_store import VectorHit

logger = logging.getLogger(__name__)


@dataclass
class FusionWeights:
    """Per-corpus blend of dense vs sparse retrievers.

    Both weights must be non-negative; the RRF score is multiplied
    by the chosen retriever's weight before summing. Setting
    ``sparse=0.0`` reduces to pure dense retrieval.
    """

    dense: float = 1.0
    sparse: float = 1.0


def reciprocal_rank_fusion(
    *,
    dense_hits: Iterable[VectorHit],
    sparse_hits: Iterable[VectorHit],
    k: int = 60,
    weights: FusionWeights | None = None,
    top_k: int = 20,
) -> list[VectorHit]:
    """Fuse two ranked lists using Reciprocal Rank Fusion.

    Parameters
    ----------
    dense_hits
        Output of :meth:`RedisVectorStore.search` (KNN, already sorted
        by similarity).
    sparse_hits
        Output of :meth:`RedisVectorStore.search_text` (BM25, sorted
        by relevance).
    k
        RRF smoothing constant (Cormack's default is 60). Larger
        values reduce the influence of low-rank items.
    weights
        Per-retriever weights. Defaults to equal weighting.
    top_k
        Maximum number of fused hits to return.
    """
    w = weights or FusionWeights()
    fused: dict[str, tuple[float, VectorHit]] = {}
    for rank, hit in enumerate(dense_hits, start=1):
        score = w.dense / (k + rank)
        prev = fused.get(hit.doc_id)
        fused[hit.doc_id] = (
            score + (prev[0] if prev else 0.0),
            prev[1] if prev else hit,
        )
    for rank, hit in enumerate(sparse_hits, start=1):
        score = w.sparse / (k + rank)
        prev = fused.get(hit.doc_id)
        fused[hit.doc_id] = (
            score + (prev[0] if prev else 0.0),
            prev[1] if prev else hit,
        )
    ranked = sorted(fused.values(), key=lambda pair: pair[0], reverse=True)
    out: list[VectorHit] = []
    for fused_score, hit in ranked[:top_k]:
        # Replace the source score with the RRF fused score so
        # downstream cosine-filters can still threshold sanely.
        hit.score = float(fused_score)
        out.append(hit)
    return out


__all__ = ["FusionWeights", "reciprocal_rank_fusion"]
