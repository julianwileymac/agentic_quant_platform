"""``alpha_factors`` RAG corpus — symbolic alpha factor formulas.

Indexes the polymorphic ``resources`` rows with
``resource_type='alpha_factor'`` so the
:class:`aqp.agents.quant.AlphaResearcher` can retrieve prior factor
proposals (with measured performance) before authoring new ones.

Source-side write path
----------------------

The :class:`AlphaResearcher` workflow upserts a ``Resource`` row per
proposed factor (Phase 8 wires the resource model). Each row carries
the symbolic formula on ``resource.meta["formula"]`` and the most
recent measured metrics on ``resource.meta["metrics"]``.

Read path (this indexer)
------------------------

Pulls the ``resources`` rows, renders one indexable paragraph per
factor, and stores them at L0 via
:class:`aqp.rag.hierarchy.HierarchicalRAG`.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.rag.chunker import Chunk
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)


def render_alpha_factor_text(payload: dict[str, Any]) -> str:
    """Render an alpha-factor resource payload into one indexable paragraph."""
    name = payload.get("name") or payload.get("slug") or "?"
    formula = (payload.get("meta") or {}).get("formula") or payload.get("formula") or ""
    rationale = (payload.get("meta") or {}).get("rationale") or payload.get("rationale") or ""
    metrics = (payload.get("meta") or {}).get("metrics") or payload.get("metrics") or {}
    parts = [
        f"Alpha factor: {name}.",
        f"Formula: {formula.strip()[:300]}" if formula else "",
        f"Rationale: {rationale.strip()[:1200]}" if rationale else "",
    ]
    if metrics:
        keys = ("sharpe", "max_drawdown", "total_return", "turnover", "ir")
        kv = ", ".join(
            f"{k}={metrics.get(k):.4f}" if isinstance(metrics.get(k), (int, float)) else f"{k}={metrics.get(k)}"
            for k in keys
            if metrics.get(k) is not None
        )
        if kv:
            parts.append(f"Metrics: {kv}.")
    tags = payload.get("tags") or []
    if tags:
        parts.append(f"Tags: {', '.join(str(t) for t in tags)}.")
    return "\n".join(p for p in parts if p)


def index_alpha_factors(
    *,
    rag: HierarchicalRAG | None = None,
    limit: int | None = 5000,
) -> int:
    """Walk ``resources`` (resource_type='alpha_factor') and index at L0."""
    rag = rag or get_default_rag()
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_resources import Resource
    except Exception:
        logger.info("Resource ORM not available; skipping alpha_factors index.")
        return 0

    items: list[tuple[Chunk, dict[str, Any]]] = []
    try:
        with SessionLocal() as session:
            query = session.query(Resource).filter(Resource.resource_type == "alpha_factor")
            if limit:
                query = query.limit(limit)
            for row in query.all():
                payload: dict[str, Any] = {
                    "id": row.id,
                    "name": row.name,
                    "slug": row.slug,
                    "tags": list(row.tags or []),
                    "meta": dict(row.meta or {}),
                }
                text = render_alpha_factor_text(payload)
                if not text:
                    continue
                meta = {
                    "doc_id": str(payload.get("id")),
                    "source_id": str(payload.get("slug") or payload.get("id")),
                    "formula": str((payload.get("meta") or {}).get("formula") or "")[:200],
                    "sharpe": str(((payload.get("meta") or {}).get("metrics") or {}).get("sharpe") or ""),
                }
                items.append(
                    (Chunk(text=text, index=0, token_count=len(text.split())), meta)
                )
    except Exception:
        logger.exception("Failed to read alpha factor resources.")
        return 0
    return rag.index_chunks("alpha_factors", items, level="l0")


__all__ = ["index_alpha_factors", "render_alpha_factor_text"]
