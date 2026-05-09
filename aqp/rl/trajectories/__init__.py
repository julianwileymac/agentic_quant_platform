"""Iceberg-backed trajectory store for RL runs.

Public surface:

- :class:`IcebergTrajectoryStore` — per-step writer used by
  :class:`aqp.rl.runtime.RLRuntime` (default trajectory store).
- :func:`ensure_duckdb_views` — create DuckDB views over the four RL
  Iceberg tables so the API ``/rl/runs/{id}/equity`` /
  ``/rl/runs/{id}/trajectories`` endpoints can return data without
  touching pyiceberg.

All writes flow through :func:`aqp.data.iceberg_catalog.append_arrow`
per the AQP data-plane rules — never call PyIceberg's
``Catalog.create_table`` / ``Table.append`` directly.
"""
from __future__ import annotations

from aqp.rl.trajectories.duckdb_views import ensure_duckdb_views, register_run_views
from aqp.rl.trajectories.iceberg_writer import (
    IcebergTrajectoryStore,
    table_identifier,
)

__all__ = [
    "IcebergTrajectoryStore",
    "ensure_duckdb_views",
    "register_run_views",
    "table_identifier",
]
