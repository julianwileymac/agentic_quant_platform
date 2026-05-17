"""Pipeline DAG and run-result dataclasses.

A :class:`Pipeline` is the materialized form of a
:class:`PipelineManifest`: real :class:`SourceNode`,
:class:`TransformNode`, :class:`SinkNode` instances ordered for
execution. The :class:`Executor` walks the chain.

The :class:`PipelineRunResult` is shaped to be a drop-in replacement
for the legacy :class:`aqp.data.pipelines.runner.IngestionReport` so
existing API routes / Celery tasks keep working when they migrate to
the engine.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aqp.data.engine.manifest import PipelineManifest
from aqp.data.engine.nodes import (
    NodeContext,
    SinkNode,
    SourceNode,
    TransformNode,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@dataclass
class PipelineRunTable:
    """Per-table outcome inside a run.

    Mirrors :class:`aqp.data.pipelines.runner.IngestionTableResult` so
    callers can treat the engine output and the legacy report
    identically.
    """

    family: str
    iceberg_identifier: str
    table_name: str
    rows_written: int = 0
    files_consumed: int = 0
    files_skipped: int = 0
    truncated: bool = False
    annotation: dict[str, Any] | None = None
    error: str | None = None
    plan: dict[str, Any] | None = None
    verifier: dict[str, Any] | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "iceberg_identifier": self.iceberg_identifier,
            "table_name": self.table_name,
            "rows_written": int(self.rows_written),
            "files_consumed": int(self.files_consumed),
            "files_skipped": int(self.files_skipped),
            "truncated": bool(self.truncated),
            "annotation": self.annotation,
            "error": self.error,
            "plan": self.plan,
            "verifier": self.verifier,
            "extras": dict(self.extras),
        }


@dataclass
class PipelineRunResult:
    """Top-level result for one pipeline run."""

    pipeline_id: str
    run_id: str
    namespace: str
    name: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    backend: str = "local"
    tables: list[PipelineRunTable] = field(default_factory=list)
    extras: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    sink_result: dict[str, Any] | None = None
    lineage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "run_id": self.run_id,
            "namespace": self.namespace,
            "name": self.name,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "backend": self.backend,
            "tables": [t.to_dict() for t in self.tables],
            "extras": list(self.extras),
            "errors": list(self.errors),
            "sink_result": dict(self.sink_result or {}),
            "lineage": dict(self.lineage),
        }

    @property
    def total_rows_written(self) -> int:
        return sum(t.rows_written for t in self.tables)


class Pipeline:
    """A materialized ``Source -> Transform* -> Sink`` chain.

    Build a :class:`Pipeline` either from a :class:`PipelineManifest`
    via :meth:`from_manifest`, or directly from node instances. The
    :class:`aqp.data.engine.executor.Executor` consumes one of these.
    """

    def __init__(
        self,
        *,
        source: SourceNode,
        transforms: list[TransformNode],
        sink: SinkNode,
        manifest: PipelineManifest | None = None,
    ) -> None:
        if not isinstance(source, SourceNode):
            raise TypeError("Pipeline.source must be a SourceNode")
        if not isinstance(sink, SinkNode):
            raise TypeError("Pipeline.sink must be a SinkNode")
        for t in transforms:
            if not isinstance(t, TransformNode):
                raise TypeError(
                    f"Pipeline.transforms entries must be TransformNode (got {t!r})"
                )
        self.source = source
        self.transforms = list(transforms)
        self.sink = sink
        self.manifest = manifest

    @classmethod
    def from_manifest(cls, manifest: PipelineManifest) -> Pipeline:
        """Build a Pipeline by resolving every NodeSpec via the registry."""
        from aqp.data.engine.registry import build_node, get_node_class
        from aqp.data.engine.nodes import NodeKind

        # Pre-validate via the registry so we fail fast with a helpful
        # error when a node alias is unknown.
        get_node_class(manifest.source.name)
        get_node_class(manifest.sink.name)
        for spec in manifest.transforms:
            get_node_class(spec.name)

        source = build_node(manifest.source.name, manifest.source.kwargs)
        if not isinstance(source, SourceNode):
            raise TypeError(
                f"manifest.source {manifest.source.name!r} resolved to non-SourceNode"
            )

        transforms: list[TransformNode] = []
        for spec in manifest.transforms:
            if not spec.enabled:
                continue
            node = build_node(spec.name, spec.kwargs)
            if not isinstance(node, TransformNode):
                raise TypeError(
                    f"manifest.transforms[{spec.name}] resolved to non-TransformNode"
                )
            transforms.append(node)

        sink = build_node(manifest.sink.name, manifest.sink.kwargs)
        if not isinstance(sink, SinkNode):
            raise TypeError(
                f"manifest.sink {manifest.sink.name!r} resolved to non-SinkNode"
            )

        # Strict mode for symmetry with the executor's expectations:
        # the registry already enforces NodeKind via the @register_node
        # decorator, but also ensure we got the right Python ABC.
        for spec, node in zip(
            (manifest.source, *manifest.transforms),
            (source, *transforms),
            strict=False,
        ):
            if spec.label is None:
                continue
            try:
                node.name = spec.label
            except Exception:  # noqa: BLE001
                pass
        try:
            if manifest.sink.label is not None:
                sink.name = manifest.sink.label
        except Exception:  # noqa: BLE001
            pass

        # Sanity check kind on the registry side.
        from aqp.data.engine.registry import _node_meta  # type: ignore

        for spec, expected in (
            (manifest.source, NodeKind.SOURCE),
            (manifest.sink, NodeKind.SINK),
        ):
            meta = _node_meta.get(spec.name)
            if meta and meta.get("kind") and meta["kind"] != expected.value:
                raise TypeError(
                    f"manifest expected {expected.value} for {spec.name!r} "
                    f"but registry recorded kind={meta['kind']!r}"
                )

        return cls(
            source=source,
            transforms=transforms,
            sink=sink,
            manifest=manifest,
        )

    # ------------------------------------------------------------------
    # Stream helpers (used by the executor)
    # ------------------------------------------------------------------

    def open_all(self, ctx: NodeContext) -> None:
        """Open every node in execution order."""
        self.source.open(ctx)
        for t in self.transforms:
            t.open(ctx)
        self.sink.open(ctx)

    def close_all(self, ctx: NodeContext) -> None:
        """Close every node in reverse execution order, swallowing errors."""
        for node in (self.sink, *reversed(self.transforms), self.source):
            try:
                node.close(ctx)
            except Exception:  # noqa: BLE001
                logger.debug("close failed for %r", node, exc_info=True)

    def stream_through(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        """Pipe ``source.stream`` through every ``transform.transform``."""
        stream: Iterator[pa.RecordBatch] = self.source.stream(ctx)
        for transform in self.transforms:
            stream = transform.transform(stream, ctx)
        return stream

    # ------------------------------------------------------------------
    # Public id helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_run_id() -> str:
        return uuid.uuid4().hex

    def make_context(
        self,
        *,
        pipeline_id: str | None = None,
        run_id: str | None = None,
        backend: Any = None,
        progress_cb: Any = None,
        chunk_rows: int = 50_000,
    ) -> NodeContext:
        return NodeContext(
            pipeline_id=pipeline_id
            or (self.manifest.id if self.manifest else "ad-hoc"),
            run_id=run_id or self.make_run_id(),
            node_name="<pipeline>",
            node_index=-1,
            backend=backend,
            progress_cb=progress_cb,
            chunk_rows=int(chunk_rows),
        )


__all__ = [
    "Pipeline",
    "PipelineRunResult",
    "PipelineRunTable",
]
