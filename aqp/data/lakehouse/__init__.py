"""Lakehouse integrations.

Phase 2e of the AQP infra-expansion plan adds Apache Hudi as an
ADDITIVE second writer for upsert-heavy market data. Iceberg remains
the canonical lakehouse write path (AGENTS rule 3): every write to
Iceberg goes through ``aqp.data.iceberg_catalog.append_arrow``.
Hudi tables live under their own ``aqp_hudi_*`` namespace prefix and
are NEVER written through ``append_arrow``.

When to use which:

- **Iceberg** (default): append-only history, broad analytics,
  Trino + Spark + Flink shared catalog, gold-tier products.
- **Hudi** (this package): upsert-heavy partitions where late-
  arriving / corrected market data has to merge in place
  (per-symbol tick streams, intraday corrections, vendor late
  arrivals).

Public surface:

- :class:`aqp.data.lakehouse.hudi.hudi_writer.HudiWriter` — pyspark-
  backed batch writer for upserts via the Hudi Spark datasource.
- :class:`aqp.data.lakehouse.hudi.hudi_streamer.HudiStreamerLauncher`
  — submits HoodieStreamer SparkApplications via the Spark Operator
  for continuous Kafka -> Hudi ingestion.
- :class:`aqp.data.datasets.kinds.hudi.HudiDataset` — Kedro-style
  read/write dataset (kind=``hudi``).
"""
from __future__ import annotations

__all__ = ["hudi"]
