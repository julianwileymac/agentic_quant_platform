"""Per-corpus indexers that pull source records and feed :class:`HierarchicalRAG`.

Each indexer is a thin function that:

1. Pulls source rows from Postgres / Iceberg.
2. Renders them as natural-language text (rows that already have a
   narrative field — complaint narratives, news bodies — are passed
   through verbatim; structured rows are formatted into a sentence).
3. Chunks the text via :mod:`aqp.rag.chunker`.
4. Calls ``rag.index_chunks(corpus, ...)``.

All indexers tolerate missing source tables — they log and return 0 so
the surrounding Celery task chain doesn't crash on cold installs.
"""
from __future__ import annotations

from aqp.rag.indexers.bars_indexer import index_bars_summary
from aqp.rag.indexers.cfpb_indexer import index_cfpb_complaints
from aqp.rag.indexers.decisions_indexer import index_decisions, render_decision_text
from aqp.rag.indexers.fda_indexer import (
    index_fda_adverse_events,
    index_fda_applications,
    index_fda_recalls,
)
from aqp.rag.indexers.fundamentals_indexer import (
    index_financial_ratios,
    index_sec_xbrl,
)
from aqp.rag.indexers.news_indexer import index_news_sentiment
from aqp.rag.indexers.performance_indexer import index_performance
from aqp.rag.indexers.sec_indexer import index_sec_filings
from aqp.rag.indexers.uspto_indexer import (
    index_uspto_assignments,
    index_uspto_patents,
    index_uspto_trademarks,
)

__all__ = [
    "index_bars_summary",
    "index_cfpb_complaints",
    "index_decisions",
    "index_fda_adverse_events",
    "index_fda_applications",
    "index_fda_recalls",
    "index_financial_ratios",
    "index_news_sentiment",
    "index_performance",
    "index_sec_filings",
    "index_sec_xbrl",
    "index_uspto_assignments",
    "index_uspto_patents",
    "index_uspto_trademarks",
    "render_decision_text",
]


INDEXER_REGISTRY = {
    "bars_daily": index_bars_summary,
    "performance": index_performance,
    "decisions": index_decisions,
    "sec_filings": index_sec_filings,
    "sec_xbrl": index_sec_xbrl,
    "financial_ratios": index_financial_ratios,
    "news_sentiment": index_news_sentiment,
    "cfpb_complaints": index_cfpb_complaints,
    "fda_applications": index_fda_applications,
    "fda_adverse_events": index_fda_adverse_events,
    "fda_recalls": index_fda_recalls,
    "uspto_patents": index_uspto_patents,
    "uspto_trademarks": index_uspto_trademarks,
    "uspto_assignments": index_uspto_assignments,
}


def get_indexer(corpus: str):
    """Return the callable that knows how to index ``corpus``."""
    if corpus not in INDEXER_REGISTRY:
        raise KeyError(
            f"No indexer registered for corpus {corpus!r}. "
            f"Known: {sorted(INDEXER_REGISTRY)}"
        )
    return INDEXER_REGISTRY[corpus]
