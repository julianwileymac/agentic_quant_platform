"""Active catalog: medallion-aware metadata + first-class lineage.

This package threads two cross-cutting concerns through every Iceberg
write:

- :mod:`aqp.data.catalog.active_metadata` — keeps
  :class:`aqp.persistence.models.DatasetCatalog` rows in sync with the
  underlying Iceberg schema, attaches business metadata
  (data_owner, semantic_definition, reliability_score, sla_class),
  and validates writes against a column-level data contract.
- :mod:`aqp.data.catalog.lineage` — :class:`LineageWriter` (Observer
  pattern) writes one ``data_lineage_events`` row per material data
  motion (Iceberg append, sink materialise, dbt build, Airbyte sync,
  MCP tool invocation).

Public symbols are re-exported here so callers can do
``from aqp.data.catalog import register_dataset, dataset, LineageWriter``
without remembering submodule paths.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from aqp.data.catalog.active_metadata import (
    BusinessMetadata,
    DataContract,
    MedallionLayer,
    RegisterDatasetResult,
    dataset,
    namespace_for_layer,
    register_dataset,
    validate_layer_for_namespace,
)
from aqp.data.catalog.lineage import (
    BaseLineageObserver,
    LineageEvent,
    LineageWriter,
    record_lineage,
)


def _load_legacy_catalog_module():
    """Load the pre-unification ``aqp/data/catalog.py`` compatibility module.

    The data-layer unification introduced ``aqp.data.catalog`` as a
    package. Python now resolves ``aqp.data.catalog`` to this directory,
    which shadows the older sibling module ``aqp/data/catalog.py``.
    Several shipped ingestion paths still import legacy helpers like
    ``register_dataset_version`` from ``aqp.data.catalog``. Load that
    file explicitly and re-export the stable public helpers here so the
    package remains backward compatible while new code uses the active
    metadata / lineage submodules.
    """
    legacy_path = Path(__file__).resolve().parents[1] / "catalog.py"
    spec = importlib.util.spec_from_file_location(
        "aqp.data._legacy_catalog_module",
        legacy_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load legacy catalog module from {legacy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_legacy_catalog = _load_legacy_catalog_module()
register_dataset_version = _legacy_catalog.register_dataset_version
register_iceberg_dataset = _legacy_catalog.register_iceberg_dataset
register_data_links = _legacy_catalog.register_data_links
upsert_instruments_for_vt_symbols = _legacy_catalog.upsert_instruments_for_vt_symbols

__all__ = [
    "BaseLineageObserver",
    "BusinessMetadata",
    "DataContract",
    "LineageEvent",
    "LineageWriter",
    "MedallionLayer",
    "RegisterDatasetResult",
    "dataset",
    "namespace_for_layer",
    "register_data_links",
    "record_lineage",
    "register_dataset",
    "register_dataset_version",
    "register_iceberg_dataset",
    "upsert_instruments_for_vt_symbols",
    "validate_layer_for_namespace",
]
