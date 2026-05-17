"""Compatibility shims that wrap the legacy ingestion path.

Existing Celery tasks and FastAPI routes depend on
:class:`aqp.data.pipelines.runner.IngestionPipeline`. To keep them
working unchanged while the engine kernel rolls out we expose:

- :func:`run_legacy_ingest_path` — same surface as
  :func:`aqp.data.pipelines.runner.run_ingest_path` but returns a
  :class:`aqp.data.engine.PipelineRunResult` so engine-aware callers
  can treat it identically.
- :func:`legacy_report_to_run_result` — mapper used internally and
  exposed for tests.
- :class:`LegacyIngestionAdapter` — a SinkNode that delegates to the
  legacy pipeline so a manifest can wrap an entire
  ``IngestionPipeline.run_path`` invocation.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, SinkNode
from aqp.data.engine.pipeline import (
    PipelineRunResult,
    PipelineRunTable,
)
from aqp.data.engine.registry import register_node

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

    from aqp.data.pipelines.runner import IngestionReport


def legacy_report_to_run_result(report: IngestionReport) -> PipelineRunResult:
    """Convert an :class:`IngestionReport` into a :class:`PipelineRunResult`.

    Run id and pipeline id are synthesized from the source path / namespace
    so the same legacy invocation always projects to a stable id.
    """
    pipeline_id = f"legacy:{report.source_path}"
    result = PipelineRunResult(
        pipeline_id=pipeline_id,
        run_id=f"legacy:{report.started_at.isoformat()}",
        namespace=report.namespace,
        name=Path(report.source_path).name or "ingest",
        started_at=report.started_at,
        finished_at=report.finished_at or datetime.utcnow(),
        backend="legacy",
        errors=list(report.errors),
        extras=list(report.extras),
        sink_result={
            "datasets_discovered": int(report.datasets_discovered),
            "director_plan": report.director_plan,
        },
    )
    for table in report.tables:
        result.tables.append(
            PipelineRunTable(
                family=table.family,
                iceberg_identifier=table.iceberg_identifier,
                table_name=table.table_name,
                rows_written=int(table.rows_written),
                files_consumed=int(table.files_consumed),
                files_skipped=int(table.files_skipped),
                truncated=bool(table.truncated),
                annotation=table.annotation,
                error=table.error,
                plan=table.plan,
                verifier=table.verifier,
            )
        )
    return result


def run_legacy_ingest_path(
    path: Path | str,
    *,
    namespace: str | None = None,
    table_prefix: str | None = None,
    annotate: bool = True,
    max_rows_per_dataset: int | None = None,
    max_files_per_dataset: int | None = None,
    progress_cb: Any = None,
    director_enabled: bool | None = None,
    allowed_namespaces: list[str] | None = None,
) -> PipelineRunResult:
    """Run the legacy IngestionPipeline and return a unified result.

    Imports the legacy module lazily so the engine can be loaded in
    environments where pyiceberg / sklearn / etc. aren't installed.
    """
    from aqp.data.pipelines.runner import run_ingest_path

    report = run_ingest_path(
        path,
        namespace=namespace,
        table_prefix=table_prefix,
        annotate=annotate,
        max_rows_per_dataset=max_rows_per_dataset,
        max_files_per_dataset=max_files_per_dataset,
        progress_cb=progress_cb,
        director_enabled=director_enabled,
        allowed_namespaces=allowed_namespaces,
    )
    return legacy_report_to_run_result(report)


@register_node("sink.legacy_ingest_path", description="Legacy IngestionPipeline.run_path adapter")
class LegacyIngestionAdapter(SinkNode):
    """Adapter sink that triggers an ``IngestionPipeline.run_path`` run.

    Useful for manifests that want to keep using the legacy
    discovery → director → materialize → annotate flow as a single
    "sink" node. The upstream Arrow stream is *consumed but ignored*;
    the actual ingestion happens inside the legacy pipeline by reading
    the ``path`` kwarg.
    """

    def __init__(
        self,
        *,
        path: str | Path,
        namespace: str | None = None,
        annotate: bool = True,
        max_rows_per_dataset: int | None = None,
        max_files_per_dataset: int | None = None,
        director_enabled: bool | None = None,
        allowed_namespaces: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.path = Path(path)
        self.namespace = namespace
        self.annotate = annotate
        self.max_rows_per_dataset = max_rows_per_dataset
        self.max_files_per_dataset = max_files_per_dataset
        self.director_enabled = director_enabled
        self.allowed_namespaces = allowed_namespaces

    def write(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> dict[str, Any]:
        # Drain any upstream batches without doing work; the legacy
        # pipeline owns its own discovery.
        for _ in _drain(batches):
            pass

        ctx.emit("legacy", f"running IngestionPipeline.run_path({self.path})")
        result = run_legacy_ingest_path(
            self.path,
            namespace=self.namespace,
            annotate=self.annotate,
            max_rows_per_dataset=self.max_rows_per_dataset,
            max_files_per_dataset=self.max_files_per_dataset,
            progress_cb=ctx.progress_cb,
            director_enabled=self.director_enabled,
            allowed_namespaces=self.allowed_namespaces,
        )
        return {
            "tables": [t.to_dict() for t in result.tables],
            "extras": list(result.extras),
            "lineage": {"legacy_run": result.run_id},
        }


def _drain(it: Iterable[Any]) -> Iterator[Any]:
    yield from it


__all__ = [
    "LegacyIngestionAdapter",
    "legacy_report_to_run_result",
    "run_legacy_ingest_path",
]
