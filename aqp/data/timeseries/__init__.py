"""Time-series database integrations.

Phase 2b of the AQP infra-expansion plan adds QuestDB as the
high-throughput hot-data tier for market.l1 / market.l2 / executions
streams. QuestDB sits next to (not in place of) Iceberg: rule 3 keeps
``iceberg_catalog.append_arrow`` as the canonical lakehouse write
path; QuestDB serves the trailing-window queries that agents need at
sub-second latency.

Public surface:

- :class:`aqp.data.timeseries.questdb_client.QuestDBClient` — async
  PGWire client (asyncpg) for reads + DDL.
- :class:`aqp.data.timeseries.questdb_ingest.QuestDBIngester` — ILP
  TCP / HTTP writer with batching for tick-data hot writes.
"""
from __future__ import annotations

__all__ = [
    "questdb_client",
    "questdb_ingest",
]
