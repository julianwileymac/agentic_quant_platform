"""Airbyte CDK extensions for the AQP self-service ingestion plane.

Public surface:

- :class:`RateLimitedHttpStream` — drop-in replacement for
  ``airbyte_cdk.sources.streams.http.HttpStream`` that consults
  :mod:`aqp_ratelimit` before every outbound request.
- :class:`PointInTimeIncrementalCursor` — incremental sync cursor
  that records the source's ``updated_at`` / ``filed_at`` and is
  safe to resume from across worker restarts (the canonical pattern
  for survivorship-bias-free backfills).
- :class:`QuestDBDestination` — Airbyte destination that writes
  through QuestDB's ILP protocol with WAL + DEDUP UPSERT KEYS
  semantics.
- :class:`IcebergBronzeDestination` — Airbyte destination that
  writes through :func:`aqp.data.iceberg_catalog.append_arrow`
  using the ``aqp_bronze_airbyte_<connector_slug>`` namespace.
- :class:`ResolverBackedConfigProvider` — feeds Airbyte config
  values from :class:`aqp.credentials.CredentialResolver` so
  connector YAML never carries plaintext API keys.
"""
from __future__ import annotations

from aqp_ingest_cdk.credentials import (
    ResolverBackedConfigProvider,
    resolve_vendor_credential,
)
from aqp_ingest_cdk.cursors import PointInTimeIncrementalCursor
from aqp_ingest_cdk.destinations import (
    IcebergBronzeDestination,
    QuestDBDestination,
)
from aqp_ingest_cdk.streams import RateLimitedHttpStream

__all__ = [
    "IcebergBronzeDestination",
    "PointInTimeIncrementalCursor",
    "QuestDBDestination",
    "RateLimitedHttpStream",
    "ResolverBackedConfigProvider",
    "resolve_vendor_credential",
]
