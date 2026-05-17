"""AQP datasets package.

Two surfaces share this package:

1. **Legacy** :mod:`aqp.data.datasets.manager` — :class:`DatasetManager`
   plus :func:`get_dataset_manager`, used by
   :mod:`aqp.api.routes.datasets` for upload / merge workflows.
   Re-exported here for backwards compatibility.
2. **Phase 0 of the self-service data fabric expansion** — Kedro-style
   typed :class:`BaseDataset` abstraction. Every readable / writable
   thing in the platform (Iceberg, parquet, REST API, partitioned
   blob, Redis key, CSV / SQL queries) has a uniform
   :class:`BaseDataset` subclass with a serialisable
   :class:`DatasetSpec` and ``_load`` / ``_save`` / ``_describe``
   methods.

The two surfaces deliberately don't overlap: the manager handles
operator-driven uploads + merges, while ``BaseDataset`` types every
catalog entry the discovery browser, the metadata cache, the Airbyte
builder codegen, and the Dagster sandbox see.

Public surface::

    from aqp.data.datasets import BaseDataset, DatasetSpec, build_dataset
    from aqp.data.datasets import register_dataset_kind, get_dataset_kind
    from aqp.data.datasets import get_dataset_manager  # legacy upload/merge

    spec = DatasetSpec(kind="iceberg", config={"identifier": "aqp_bronze_demo.bars"})
    dataset = build_dataset(spec)
    table = dataset.load()
"""
from __future__ import annotations

# The kinds package self-registers via the metaclass on import; keep
# the import-on-attribute chain compact.
from aqp.data.datasets.base import BaseDataset
from aqp.data.datasets.exceptions import (
    DatasetKindUnknown,
    DatasetNotMaterialized,
    DatasetSaveDisabled,
)
from aqp.data.datasets.registry import (
    build_dataset,
    get_dataset_kind,
    iter_dataset_kinds,
    register_dataset_kind,
)
from aqp.data.datasets.spec import DatasetSpec, MedallionLayer

# Importing the kinds module is what triggers their auto-registration
# via :class:`BaseDataset.__init_subclass__`. Done at the bottom so the
# registry symbols above are available when the kinds resolve their
# imports.
from aqp.data.datasets import kinds as _kinds  # noqa: F401  (side-effect import)

# Backwards-compatible re-exports for the legacy upload/merge surface.
# These predate the data fabric expansion; ``aqp.api.routes.datasets``
# still imports ``get_dataset_manager`` from this package.
from aqp.data.datasets.manager import (
    DatasetManager,
    MergeJob,
    StagedUpload,
    UploadResult,
    get_dataset_manager,
)

__all__ = [
    "BaseDataset",
    "DatasetKindUnknown",
    "DatasetManager",
    "DatasetNotMaterialized",
    "DatasetSaveDisabled",
    "DatasetSpec",
    "MedallionLayer",
    "MergeJob",
    "StagedUpload",
    "UploadResult",
    "build_dataset",
    "get_dataset_kind",
    "get_dataset_manager",
    "iter_dataset_kinds",
    "register_dataset_kind",
]
