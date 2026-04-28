"""Dagster assets exposed by the AQP code location."""
from __future__ import annotations

from aqp.dagster.assets import airbyte, catalog, compaction, entities, profiling, sources

ASSET_MODULES = (sources, entities, catalog, profiling, compaction, airbyte)


def all_assets() -> list:
    """Aggregate every asset across the modules."""
    items: list = []
    for module in ASSET_MODULES:
        for attr in vars(module).values():
            asset_def = getattr(attr, "asset_def", None) or getattr(attr, "key", None)
            if asset_def is None and not callable(attr):
                continue
            # Dagster decorates with attribute ``op``; treat ``@asset``-wrapped
            # callables as assets when they have ``op`` or ``key``.
            if hasattr(attr, "op") and hasattr(attr, "key"):
                items.append(attr)
    return items


__all__ = ["ASSET_MODULES", "all_assets"]
