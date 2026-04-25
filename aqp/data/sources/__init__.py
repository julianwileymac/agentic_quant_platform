"""Unified data-source adapter package.

This package sits alongside the legacy :mod:`aqp.data.ingestion` adapters
(``YahooFinanceSource``, ``PolygonSource``, ``AlphaVantageSource``,
``IBKRHistoricalSource``, ``LocalCSVSource``, ``LocalParquetSource``) and
the :mod:`aqp.data.news` providers. It adds a richer :class:`DataSourceAdapter`
contract with a :class:`DataDomain` taxonomy, a :class:`DataSource`
registry-backed resolver for identifier graphs, and first-class adapters
for FRED, SEC EDGAR and GDelt.

Nothing in this package *replaces* the legacy adapters — they continue
to work unchanged. Instead, the new adapters emit :class:`DatasetVersion`,
:class:`IdentifierLink`, and :class:`DataLink` rows in addition to Parquet
writes so cross-source queries ("what data do we have for AAPL?") become
trivial.
"""
from __future__ import annotations

from aqp.data.sources.base import (
    DataSourceAdapter,
    IdentifierSpec,
    ProbeResult,
)
from aqp.data.sources.domains import DataDomain
from aqp.data.sources.registry import (
    get_data_source,
    list_data_sources,
    set_data_source_enabled,
    upsert_data_source,
)
from aqp.data.sources.resolvers.identifiers import IdentifierResolver

__all__ = [
    "DataDomain",
    "DataSourceAdapter",
    "IdentifierResolver",
    "IdentifierSpec",
    "ProbeResult",
    "get_data_source",
    "list_data_sources",
    "set_data_source_enabled",
    "upsert_data_source",
]
