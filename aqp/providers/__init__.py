"""OpenBB-style provider pattern: ``Fetcher[Q, R]`` + ``QueryParams`` + ``Data``.

Every research-data flow in the platform can (optionally) be authored as a
:class:`Fetcher` subclass that declares its typed query + return shape. The
standard_models in :mod:`aqp.providers.standard_models` supply the canonical
schemas; concrete provider fetchers (FMP, AlphaVantage, yfinance, Intrinio,
…) subclass those schemas and implement ``transform_query`` /
``extract_data`` / ``transform_data`` — identical to OpenBB.

Why layer this on top of the existing :class:`aqp.data.sources.base.DataSourceAdapter`?
- Adapters remain a good fit for *bulk* ingestion flows (FRED series dumps,
  SEC filings index, GDelt manifest slices) that materialise Parquet + emit
  lineage rows.
- Fetchers are the right fit for *typed* spot requests the UI or agents
  make ("give me AAPL's Q4 2025 balance sheet", "list upcoming earnings for
  XLF constituents").

Both flows share the ``data_sources`` registry — a ``Fetcher`` declares its
``vendor_key`` which maps 1:1 to a ``data_sources.name`` row.
"""
from aqp.providers.base import (
    AnnotatedResult,
    CostTier,
    Data,
    Fetcher,
    QueryParams,
)
from aqp.providers.catalog import (
    FetcherCatalog,
    fetcher_catalog,
    list_fetchers,
    pick_fetcher,
    register_fetcher,
)
from aqp.providers import alpha_vantage as alpha_vantage

__all__ = [
    "AnnotatedResult",
    "CostTier",
    "Data",
    "Fetcher",
    "FetcherCatalog",
    "QueryParams",
    "fetcher_catalog",
    "list_fetchers",
    "pick_fetcher",
    "register_fetcher",
    "alpha_vantage",
]
