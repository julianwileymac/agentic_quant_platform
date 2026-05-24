"""Polygon.io connectors.

Four streams cover the most common AQP use-cases:

- :class:`PolygonAggregatesStream` — minute/hour/day OHLCV bars
  (incremental, append+dedup).
- :class:`PolygonTradesStream` — tick-level trades (incremental,
  append-only).
- :class:`PolygonQuotesStream` — top-of-book quotes (incremental,
  append-only).
- :class:`PolygonOptionsChainStream` — listed options chain
  snapshots (incremental, append+dedup).

Every stream resolves the calling user's BYOK Polygon API key via
:class:`aqp_ingest_cdk.credentials.ResolverBackedConfigProvider`
and debits the matching ``polygon.<endpoint>`` bucket on every
HTTP request.
"""
from __future__ import annotations

from aqp_ingest.connectors.polygon.aggregates import PolygonAggregatesStream
from aqp_ingest.connectors.polygon.options_chain import PolygonOptionsChainStream
from aqp_ingest.connectors.polygon.quotes import PolygonQuotesStream
from aqp_ingest.connectors.polygon.trades import PolygonTradesStream

__all__ = [
    "PolygonAggregatesStream",
    "PolygonOptionsChainStream",
    "PolygonQuotesStream",
    "PolygonTradesStream",
]
