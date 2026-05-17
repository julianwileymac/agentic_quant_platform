"""Unified node-graph data engine.

The engine kernel is the single declarative entry point for every
ingestion path in AQP. A :class:`PipelineManifest` describes a
``Source -> Transform* -> Sink`` chain plus a compute backend choice
(``local`` / ``dask`` / ``ray``). An :class:`Executor` walks the chain,
streams Arrow ``RecordBatch`` slices through each node, and writes a
:class:`PipelineRunResult` shaped to be a drop-in replacement for the
legacy :class:`aqp.data.pipelines.runner.IngestionReport`.

Public surface:

- :class:`SourceNode`, :class:`TransformNode`, :class:`SinkNode`
- :class:`Pipeline`, :class:`PipelineRunResult`, :class:`PipelineRunTable`
- :class:`PipelineManifest`, :class:`NodeSpec`, :class:`ComputeSpec`,
  :class:`SchedulingSpec`
- :class:`LocalExecutor`, :class:`DaskExecutor`, :class:`RayExecutor`,
  :func:`build_executor`
- :func:`register_node`, :func:`get_node_class`, :func:`list_nodes`,
  :func:`build_node`
- :func:`run_legacy_ingest_path` — compatibility shim over the existing
  ``IngestionPipeline.run_path`` (lives in :mod:`aqp.data.engine.compat`).
"""
from __future__ import annotations

from aqp.data.engine.compat import (
    LegacyIngestionAdapter,
    legacy_report_to_run_result,
    run_legacy_ingest_path,
)
from aqp.data.engine.executor import (
    DaskExecutor,
    Executor,
    LocalExecutor,
    RayExecutor,
    build_executor,
)
from aqp.data.engine.manifest import (
    ComputeBackendKind,
    ComputeSpec,
    NodeSpec,
    PartitionSpec,
    PipelineManifest,
    SchedulingSpec,
)
from aqp.data.engine.nodes import (
    NodeContext,
    NodeKind,
    SinkNode,
    SourceNode,
    TransformNode,
)
from aqp.data.engine.pipeline import (
    Pipeline,
    PipelineRunResult,
    PipelineRunTable,
)
from aqp.data.engine.registry import (
    build_node,
    get_node_class,
    list_nodes,
    list_nodes_by_kind,
    register_node,
)
from aqp.data.engine.airbyte import build_airbyte_staging_manifest

__all__ = [
    "build_airbyte_staging_manifest",
    "ComputeBackendKind",
    "ComputeSpec",
    "DaskExecutor",
    "Executor",
    "LegacyIngestionAdapter",
    "LocalExecutor",
    "NodeContext",
    "NodeKind",
    "NodeSpec",
    "PartitionSpec",
    "Pipeline",
    "PipelineManifest",
    "PipelineRunResult",
    "PipelineRunTable",
    "RayExecutor",
    "SchedulingSpec",
    "SinkNode",
    "SourceNode",
    "TransformNode",
    "build_executor",
    "build_node",
    "get_node_class",
    "legacy_report_to_run_result",
    "list_nodes",
    "list_nodes_by_kind",
    "register_node",
    "run_legacy_ingest_path",
]
