"""Query intent → :class:`aqp.rag.RAGPlan` router.

A small, deterministic router that turns a natural-language query +
optional explicit knobs into a query plan over the hierarchy. Used by
the API layer and by agents that don't want to manage filters by hand.

The mapping is intentionally simple — the LLM/agent layer handles the
hard cases (paper Section 3.2 autonomous walk uses ``HierarchicalRAG.walk``
directly).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from aqp.rag.hierarchy import RAGPlan
from aqp.rag.orders import KnowledgeOrder

logger = logging.getLogger(__name__)


_FIRST_HINTS = ("price", "volume", "bar", "intraday", "performance", "drawdown", "sharpe", "return")
_SECOND_HINTS = ("filing", "10-k", "10-q", "8-k", "earnings", "fundament", "ratio", "balance sheet", "cash flow")
_THIRD_HINTS = ("complaint", "cfpb", "fda", "recall", "patent", "trademark", "uspto", "adverse")

_VT_SYMBOL_RE = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{2,5})?\b")
_AS_OF_RE = re.compile(r"\b(\d{4}(?:-\d{2}(?:-\d{2})?)?)\b")


def infer_orders(query: str) -> tuple[KnowledgeOrder, ...]:
    """Heuristically pick which knowledge orders are relevant."""
    q = query.lower()
    out: list[KnowledgeOrder] = []
    if any(h in q for h in _FIRST_HINTS):
        out.append("first")
    if any(h in q for h in _SECOND_HINTS):
        out.append("second")
    if any(h in q for h in _THIRD_HINTS):
        out.append("third")
    return tuple(out) if out else ("first", "second", "third")


def infer_vt_symbol(query: str) -> str | None:
    m = _VT_SYMBOL_RE.search(query)
    return m.group(0) if m else None


def infer_as_of(query: str) -> str | None:
    m = _AS_OF_RE.search(query)
    return m.group(1) if m else None


def route_query(
    query: str,
    *,
    levels: Sequence[str] | None = None,
    orders: Sequence[KnowledgeOrder] | None = None,
    vt_symbol: str | None = None,
    as_of_prefix: str | None = None,
    per_level_k: int = 5,
    final_k: int = 8,
    rerank: bool = True,
    compress: bool = True,
) -> RAGPlan:
    """Return a :class:`RAGPlan` for ``query``.

    Hints (orders, vt_symbol, as_of) are inferred from the query text
    when not explicitly provided. The default plan walks all four
    levels.
    """
    return RAGPlan(
        query=query,
        levels=tuple(levels) if levels else ("l0", "l1", "l2", "l3"),
        orders=tuple(orders) if orders else infer_orders(query),
        vt_symbol=vt_symbol or infer_vt_symbol(query),
        as_of_prefix=as_of_prefix or infer_as_of(query),
        per_level_k=per_level_k,
        final_k=final_k,
        rerank=rerank,
        compress=compress,
    )


__all__ = [
    "infer_as_of",
    "infer_orders",
    "infer_vt_symbol",
    "route_query",
]
