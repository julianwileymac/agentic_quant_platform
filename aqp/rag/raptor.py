"""RAPTOR-style hierarchical clustering + summarisation.

Port of FinGPT's ``Raptor`` (see
``inspiration/FinGPT-master/fingpt/FinGPT_FinancialReportAnalysis/utils/rag.py``)
with three improvements:

1. UMAP / scikit-learn / LLM summariser are all optional — if anything
   isn't installed we degrade gracefully (UMAP -> identity, GMM ->
   k-means via numpy, summariser -> first-N tokens).
2. Summaries are emitted via ``router_complete`` so they participate in
   the platform's cost / provider routing.
3. Returns plain dataclasses so the result can be persisted into Redis
   alongside the leaf chunks at higher levels.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RaptorNode:
    """One node in the RAPTOR hierarchy."""

    level: int
    cluster_id: int
    text: str
    member_ids: list[str] = field(default_factory=list)
    child_node_ids: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RaptorTree:
    """Result of hierarchical clustering + summarisation."""

    leaves: list[str]
    nodes: dict[str, RaptorNode] = field(default_factory=dict)


_SUMMARY_SYSTEM = (
    "You are a senior research analyst. Summarise the following document "
    "snippets into one cohesive paragraph (180 tokens max). Preserve key "
    "numbers, names, and dates. Do not invent facts."
)


def _project(vectors: list[list[float]], target_dim: int = 10) -> list[list[float]]:
    if not vectors or len(vectors[0]) <= target_dim:
        return vectors
    try:
        import numpy as np  # type: ignore[import-not-found]
        import umap  # type: ignore[import-not-found]

        arr = np.asarray(vectors, dtype="float32")
        n_neighbors = max(2, min(15, len(vectors) - 1))
        reducer = umap.UMAP(
            n_neighbors=n_neighbors,
            n_components=min(target_dim, len(vectors) - 1),
            metric="cosine",
            random_state=42,
        )
        return reducer.fit_transform(arr).tolist()
    except Exception:  # pragma: no cover - umap is optional
        logger.debug("UMAP unavailable; skipping projection.", exc_info=True)
        return vectors


def _cluster(
    projected: list[list[float]],
    *,
    k_max: int = 8,
) -> list[int]:
    n = len(projected)
    if n <= 1:
        return [0] * n
    k = max(2, min(k_max, int(math.ceil(math.sqrt(n / 2)))))
    try:
        import numpy as np  # type: ignore[import-not-found]
        from sklearn.mixture import GaussianMixture  # type: ignore[import-not-found]

        arr = np.asarray(projected, dtype="float32")
        gm = GaussianMixture(n_components=k, random_state=42, covariance_type="full")
        gm.fit(arr)
        return gm.predict(arr).tolist()
    except Exception:
        logger.debug("scikit-learn / GMM unavailable; using simple k-means.", exc_info=True)

    # Pure-python k-means fallback (Lloyd's, 10 iterations).
    centroids = [list(projected[i]) for i in range(k)]
    labels = [0] * n
    for _ in range(10):
        # assign
        for i, vec in enumerate(projected):
            labels[i] = min(
                range(k),
                key=lambda c: sum(
                    (vec[d] - centroids[c][d]) ** 2 for d in range(len(vec))
                ),
            )
        # update
        for c in range(k):
            members = [projected[i] for i in range(n) if labels[i] == c]
            if not members:
                continue
            centroids[c] = [
                sum(v[d] for v in members) / len(members)
                for d in range(len(members[0]))
            ]
    return labels


def _summarize(
    snippets: Sequence[str],
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 220,
) -> str:
    text = "\n\n".join(s.strip() for s in snippets if s)
    if not text:
        return ""
    try:
        from aqp.config import settings as _settings
        from aqp.llm.providers.router import router_complete

        prov = provider or _settings.llm_provider
        mdl = model or _settings.llm_quick_model
        result = router_complete(
            provider=prov,
            model=mdl,
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {"role": "user", "content": text[:8000]},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            tier="quick",
        )
        return (result.content or "").strip()
    except Exception:  # noqa: BLE001
        logger.exception("RAPTOR summariser failed; using truncated extract.")
        words = text.split()
        return " ".join(words[: max_tokens * 4])


def build_tree(
    *,
    leaf_ids: Sequence[str],
    leaf_texts: Sequence[str],
    leaf_vectors: Sequence[Sequence[float]],
    max_levels: int = 3,
    k_max: int = 8,
    provider: str | None = None,
    model: str | None = None,
) -> RaptorTree:
    """Build a RAPTOR tree by recursive UMAP+GMM clustering and summarisation.

    Each non-leaf node text is an LLM-written summary of its members'
    text. Returns a flat dict keyed by ``"L{level}#C{cluster_id}"``.
    """
    if not leaf_ids:
        return RaptorTree(leaves=[])
    if len(leaf_ids) != len(leaf_texts) or len(leaf_ids) != len(leaf_vectors):
        raise ValueError("leaf_ids / leaf_texts / leaf_vectors length mismatch")

    tree = RaptorTree(leaves=list(leaf_ids))
    current_ids = list(leaf_ids)
    current_texts = list(leaf_texts)
    current_vectors = [list(v) for v in leaf_vectors]
    level = 0
    while level < max_levels and len(current_ids) > 2:
        level += 1
        projected = _project(current_vectors, target_dim=min(10, len(current_vectors) - 1))
        labels = _cluster(projected, k_max=k_max)
        unique = sorted(set(labels))
        if len(unique) <= 1:
            break
        next_ids: list[str] = []
        next_texts: list[str] = []
        next_vectors: list[list[float]] = []
        for c in unique:
            members = [i for i, lbl in enumerate(labels) if lbl == c]
            if not members:
                continue
            member_ids = [current_ids[i] for i in members]
            member_texts = [current_texts[i] for i in members]
            summary = _summarize(member_texts, provider=provider, model=model)
            node_id = f"L{level}#C{c}"
            node = RaptorNode(
                level=level,
                cluster_id=int(c),
                text=summary,
                member_ids=list(member_ids),
            )
            tree.nodes[node_id] = node
            next_ids.append(node_id)
            next_texts.append(summary)
            # centroid as the new vector
            centroid = [
                sum(current_vectors[i][d] for i in members) / len(members)
                for d in range(len(current_vectors[0]))
            ]
            next_vectors.append(centroid)
        current_ids, current_texts, current_vectors = next_ids, next_texts, next_vectors
    return tree


__all__ = [
    "RaptorNode",
    "RaptorTree",
    "build_tree",
]
