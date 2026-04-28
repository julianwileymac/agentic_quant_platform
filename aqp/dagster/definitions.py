"""Aggregate :class:`Definitions` for the AQP Dagster code location.

The cluster's ``pipelines-user-code`` Helm deployment loads this
module via ``dagster api grpc -m aqp.dagster.definitions``.
"""
from __future__ import annotations

from dagster import Definitions

from aqp.dagster.assets import (
    airbyte as airbyte_assets,
    catalog as catalog_assets,
    compaction as compaction_assets,
    entities as entity_assets,
    profiling as profiling_assets,
    sources as source_assets,
)
from aqp.dagster.jobs import ALL_JOBS
from aqp.dagster.resources import build_resources
from aqp.dagster.schedules import ALL_SCHEDULES
from aqp.dagster.sensors import ALL_SENSORS

_ASSETS = []
for module in (
    source_assets,
    entity_assets,
    catalog_assets,
    profiling_assets,
    compaction_assets,
    airbyte_assets,
):
    for value in vars(module).values():
        if hasattr(value, "op") and hasattr(value, "key"):
            _ASSETS.append(value)

defs = Definitions(
    assets=_ASSETS,
    jobs=ALL_JOBS,
    schedules=ALL_SCHEDULES,
    sensors=ALL_SENSORS,
    resources=build_resources(),
)


__all__ = ["defs"]
