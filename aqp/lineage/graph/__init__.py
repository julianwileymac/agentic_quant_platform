"""Bipartite lineage DAG package (Workstream A).

Re-exports the public surface:

- :class:`LineageGraphWriter` — single sanctioned writer for the
  ``lineage_dataset_vertex`` / ``lineage_transform_vertex`` /
  ``lineage_edge`` triple.
- :class:`BipartiteGraphObserver` — :class:`BaseLineageObserver`
  subclass that subscribes to the existing
  :class:`aqp.data.catalog.lineage.LineageBus` and dual-writes into
  the graph tables.
- :func:`iceberg_snapshot_address` — content-address helper for
  Iceberg-backed datasets.
- :func:`register_bipartite_observer` — idempotent boot helper called
  from FastAPI / Celery startup.
"""
from __future__ import annotations

from aqp.lineage.graph.content_address import (
    fallback_content_hash,
    iceberg_snapshot_address,
)
from aqp.lineage.graph.observer import (
    BipartiteGraphObserver,
    is_bipartite_graph_enabled,
    register_bipartite_observer,
)
from aqp.lineage.graph.writer import (
    LineageGraphWriter,
    get_default_graph_writer,
)

__all__ = [
    "BipartiteGraphObserver",
    "LineageGraphWriter",
    "fallback_content_hash",
    "get_default_graph_writer",
    "iceberg_snapshot_address",
    "is_bipartite_graph_enabled",
    "register_bipartite_observer",
]
