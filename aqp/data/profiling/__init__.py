"""Arrow-native dataset profiling.

Two layers:

- :func:`compute_profile` — scan a :class:`pa.Table` (optionally via a
  Dask / Ray backend) and produce a structured summary (column count,
  null fractions, distinct estimates, min/max, top-K).
- :func:`write_profile` / :func:`read_profile` — Redis-backed cache
  with a Postgres mirror in ``dataset_profiles``.

Hooks:

- :func:`refresh_table_profile` is invoked by
  :class:`aqp.data.fetchers.sinks.iceberg_sink.IcebergSink` after a
  successful materialization.
"""
from __future__ import annotations

from aqp.data.profiling.cache import (
    delete_profile,
    read_profile,
    refresh_table_profile,
    write_profile,
)
from aqp.data.profiling.profiler import compute_profile, profile_iceberg_table

__all__ = [
    "compute_profile",
    "delete_profile",
    "profile_iceberg_table",
    "read_profile",
    "refresh_table_profile",
    "write_profile",
]
