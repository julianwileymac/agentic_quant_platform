"""Hierarchical Retrieval-Augmented Generation on Redis (Alpha-GPT style).

This package implements the four-level hierarchical RAG described in
*Alpha-GPT: Human-AI Interactive Alpha Mining* ([2308.00016v2.pdf]).

Levels
------

- **L0 — Alpha / Decision base** (paper RAG#0): past ``agent_decisions``,
  ``equity_reports``, and ``backtest_runs`` outcomes, used to learn the
  characteristics of previously successful alphas / decisions.
- **L1 — High-level categories** (paper RAG#1): top-level domain such as
  ``price_volume``, ``fundamental``, ``news_sentiment``, ``regulatory``.
- **L2 — Sub-categories** (paper RAG#2): ``earnings_call``, ``disclosures``,
  ``insider``, ``cfpb_complaint``, ``fda_recall``, ``patent_grant``...
- **L3 — Specific data fields / chunks** (paper RAG#3): individual
  field descriptions, document chunks, complaint narratives.

Orders (data tiers)
-------------------

Orthogonal to the levels, knowledge is grouped into three "orders"
matching the user's research-agent specification:

- **first** — bars / trades / performance (price-volume primitives).
- **second** — SEC filings / fundamentals / ratios.
- **third** — CFPB complaints / FDA applications + adverse events /
  USPTO patents + trademarks.

Public API
----------

- :class:`HierarchicalRAG` — top-level facade; ``query`` / ``walk`` /
  ``index_chunk`` / ``precompute_l0_alpha_base``.
- :func:`get_default_rag` — process-wide cached instance.

All vector storage, BM25 caches, and reflection logs go through the
single Redis instance configured by :attr:`aqp.config.Settings.redis_url`.
Chroma is **not** replaced; it stays for dataset/code metadata indexing.
"""
from __future__ import annotations

from aqp.rag.hierarchy import HierarchicalRAG, RAGHit, RAGPlan, get_default_rag
from aqp.rag.orders import (
    KNOWLEDGE_ORDERS,
    KnowledgeOrder,
    OrderCorpus,
    corpora_for_order,
    order_for_corpus,
)
from aqp.rag.redis_store import RedisVectorStore

__all__ = [
    "HierarchicalRAG",
    "KNOWLEDGE_ORDERS",
    "KnowledgeOrder",
    "OrderCorpus",
    "RAGHit",
    "RAGPlan",
    "RedisVectorStore",
    "corpora_for_order",
    "get_default_rag",
    "order_for_corpus",
]
