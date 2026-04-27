"""Generic file / folder / ZIP ingestion into the Iceberg catalog.

Public entry points:

- :class:`IngestionPipeline` — orchestrator, wires discovery → extract →
  materialize → annotate.
- :func:`run_ingest_path` — convenience wrapper around the pipeline.
- :class:`DiscoveredDataset` — dataclass returned by the discovery step.
- :class:`IngestionReport` — dataclass returned by the runner.
"""
from __future__ import annotations

from aqp.data.pipelines.director import (
    IngestionPlan,
    PlannedDataset,
    VerifierVerdict,
    plan_ingestion,
    verify_after_materialise,
)
from aqp.data.pipelines.discovery import (
    DiscoveredDataset,
    DiscoveredMember,
    discover_datasets,
)
from aqp.data.pipelines.runner import (
    IngestionPipeline,
    IngestionReport,
    IngestionTableResult,
    run_ingest_path,
)

__all__ = [
    "DiscoveredDataset",
    "DiscoveredMember",
    "IngestionPipeline",
    "IngestionPlan",
    "IngestionReport",
    "IngestionTableResult",
    "PlannedDataset",
    "VerifierVerdict",
    "discover_datasets",
    "plan_ingestion",
    "run_ingest_path",
    "verify_after_materialise",
]
