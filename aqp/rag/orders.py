"""Knowledge orders + corpus taxonomy.

The user's research-agent specification splits knowledge into three
"orders" (independent of the four Alpha-GPT RAG levels):

- **first**  — price/trade time-series and performance data.
- **second** — SEC filings, financial ratios, fundamentals.
- **third**  — CFPB complaints, FDA applications + adverse events /
  recalls, USPTO patents + trademarks (plus assignments).

Each order carries a fixed set of corpora. Each corpus is bound to:

- A canonical L1/L2 path so the :class:`HierarchicalRAG` knows where
  hits should land.
- An optional Iceberg ``namespace.table`` reference used by the
  per-corpus indexers under :mod:`aqp.rag.indexers` to pull source
  records.

Adding a new corpus is a one-line entry to :data:`OrderCatalog`. Do
**not** mutate this table at runtime — the indexers and routes import
it at module load.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


KnowledgeOrder = Literal["first", "second", "third"]
KNOWLEDGE_ORDERS: tuple[KnowledgeOrder, ...] = ("first", "second", "third")


@dataclass(frozen=True)
class OrderCorpus:
    """Static descriptor for a single RAG corpus.

    Attributes
    ----------
    name:
        Unique slug used as Redis tag and indexer key (e.g. ``"sec_filings"``).
    order:
        ``first`` | ``second`` | ``third``.
    l1:
        High-level category (paper RAG#1).
    l2:
        Sub-category (paper RAG#2). ``""`` if the corpus only lives at L1.
    iceberg:
        Optional ``namespace.table`` reference for the indexer.
    description:
        One-sentence purpose used in the L1/L2 navigation prompts.
    """

    name: str
    order: KnowledgeOrder
    l1: str
    l2: str
    iceberg: str | None
    description: str


# fmt: off
OrderCatalog: tuple[OrderCorpus, ...] = (
    # --- first order: price-volume + performance -----------------------
    OrderCorpus(
        name="bars_minute",
        order="first",
        l1="price_volume",
        l2="intraday_bars",
        iceberg="aqp_alpha_vantage.time_series_intraday",
        description="Minute-resolution OHLCV bars and derived microstructure features.",
    ),
    OrderCorpus(
        name="bars_daily",
        order="first",
        l1="price_volume",
        l2="daily_bars",
        iceberg="aqp_alpha_vantage.time_series_daily_adjusted",
        description="Daily OHLCV bars (split + dividend adjusted) for the universe.",
    ),
    OrderCorpus(
        name="performance",
        order="first",
        l1="price_volume",
        l2="performance",
        iceberg=None,
        description="Past backtest / paper / live PnL metrics keyed by strategy.",
    ),
    OrderCorpus(
        name="decisions",
        order="first",
        l1="alpha_base",
        l2="agent_decisions",
        iceberg=None,
        description="Past agent decisions with realized outcomes (paper RAG#0 alpha base).",
    ),
    # --- second order: SEC + fundamentals ------------------------------
    OrderCorpus(
        name="sec_filings",
        order="second",
        l1="fundamental",
        l2="disclosures",
        iceberg=None,
        description="SEC EDGAR filings index (10-K, 10-Q, 8-K, S-1...).",
    ),
    OrderCorpus(
        name="sec_xbrl",
        order="second",
        l1="fundamental",
        l2="standardized_financials",
        iceberg=None,
        description="Standardized XBRL financial statements per filing.",
    ),
    OrderCorpus(
        name="financial_ratios",
        order="second",
        l1="fundamental",
        l2="ratios",
        iceberg=None,
        description="Computed ratios (P/E, ROE, current ratio, ...).",
    ),
    OrderCorpus(
        name="earnings_call",
        order="second",
        l1="fundamental",
        l2="earnings_call",
        iceberg=None,
        description="Quarterly earnings call transcripts (raw + Q&A split).",
    ),
    OrderCorpus(
        name="news_sentiment",
        order="second",
        l1="news_sentiment",
        l2="news_articles",
        iceberg="aqp_alpha_vantage.intelligence_news_sentiment",
        description="Multi-source financial news with scored sentiment.",
    ),
    # --- third order: regulatory ---------------------------------------
    OrderCorpus(
        name="cfpb_complaints",
        order="third",
        l1="regulatory",
        l2="cfpb_complaint",
        iceberg="aqp_cfpb.complaints",
        description="CFPB Consumer Complaint Database narratives by company.",
    ),
    OrderCorpus(
        name="fda_applications",
        order="third",
        l1="regulatory",
        l2="fda_application",
        iceberg="aqp_fda.applications",
        description="FDA drug + device application submissions and approvals.",
    ),
    OrderCorpus(
        name="fda_adverse_events",
        order="third",
        l1="regulatory",
        l2="fda_adverse_event",
        iceberg="aqp_fda.adverse_events",
        description="FDA FAERS / MAUDE adverse event reports linked to issuers.",
    ),
    OrderCorpus(
        name="fda_recalls",
        order="third",
        l1="regulatory",
        l2="fda_recall",
        iceberg="aqp_fda.recalls",
        description="FDA enforcement recalls (Class I/II/III) per product.",
    ),
    OrderCorpus(
        name="uspto_patents",
        order="third",
        l1="regulatory",
        l2="patent_grant",
        iceberg="aqp_uspto.patents",
        description="USPTO granted patents with assignee linkage to issuers.",
    ),
    OrderCorpus(
        name="uspto_trademarks",
        order="third",
        l1="regulatory",
        l2="trademark",
        iceberg="aqp_uspto.trademarks",
        description="USPTO trademark applications and registrations per issuer.",
    ),
    OrderCorpus(
        name="uspto_assignments",
        order="third",
        l1="regulatory",
        l2="patent_assignment",
        iceberg="aqp_uspto.assignments",
        description="USPTO patent assignment events (M&A signal).",
    ),
)
# fmt: on


_BY_NAME: dict[str, OrderCorpus] = {c.name: c for c in OrderCatalog}


def list_corpora() -> tuple[OrderCorpus, ...]:
    """Return every registered corpus in declaration order."""
    return OrderCatalog


def get_corpus(name: str) -> OrderCorpus:
    """Look up a corpus by its slug. Raises ``KeyError`` if unknown."""
    try:
        return _BY_NAME[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown corpus {name!r}. Known: {sorted(_BY_NAME)}"
        ) from exc


def corpora_for_order(order: KnowledgeOrder) -> tuple[OrderCorpus, ...]:
    """Return every corpus belonging to ``order``."""
    return tuple(c for c in OrderCatalog if c.order == order)


def corpora_for_l1(l1: str) -> tuple[OrderCorpus, ...]:
    """Return every corpus tagged with the given high-level category."""
    return tuple(c for c in OrderCatalog if c.l1 == l1)


def order_for_corpus(name: str) -> KnowledgeOrder:
    """Return the order a corpus belongs to."""
    return get_corpus(name).order


def l1_categories() -> tuple[str, ...]:
    """Distinct L1 category slugs in declaration order."""
    seen: dict[str, None] = {}
    for c in OrderCatalog:
        seen.setdefault(c.l1, None)
    return tuple(seen)


def l2_categories(l1: str | None = None) -> tuple[str, ...]:
    """Distinct L2 category slugs, optionally scoped to one L1."""
    seen: dict[str, None] = {}
    for c in OrderCatalog:
        if c.l2 and (l1 is None or c.l1 == l1):
            seen.setdefault(c.l2, None)
    return tuple(seen)


__all__ = [
    "KNOWLEDGE_ORDERS",
    "KnowledgeOrder",
    "OrderCatalog",
    "OrderCorpus",
    "corpora_for_l1",
    "corpora_for_order",
    "get_corpus",
    "l1_categories",
    "l2_categories",
    "list_corpora",
    "order_for_corpus",
]
