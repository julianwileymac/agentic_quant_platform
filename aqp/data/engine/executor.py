"""Executors that walk a :class:`Pipeline` end-to-end.

Three flavors:

- :class:`LocalExecutor` — single-process, single-thread; pure PyArrow.
- :class:`DaskExecutor` — submits the source/transform pipeline to a
  Dask cluster and consumes the result back as Arrow batches.
- :class:`RayExecutor` — same idea on Ray.

The Dask / Ray executors degrade gracefully to the local backend when
the optional deps aren't importable, so importing this module never
fails on a minimal install.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aqp.data.engine.manifest import ComputeBackendKind, ComputeSpec, PipelineManifest
from aqp.data.engine.nodes import NodeContext
from aqp.data.engine.pipeline import (
    Pipeline,
    PipelineRunResult,
    PipelineRunTable,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aqp.data.compute.backend import ComputeBackend


ProgressCallback = Callable[..., None]


class Executor:
    """Base executor shared by the local / dask / ray flavors."""

    backend_label: str = "local"

    def __init__(
        self,
        *,
        compute: ComputeSpec | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        self.compute = compute or ComputeSpec()
        self.progress_cb = progress_cb

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def execute(self, pipeline: Pipeline) -> PipelineRunResult:
        """Walk the pipeline source -> transforms -> sink and collect a result."""
        backend = self._make_backend()
        ctx = pipeline.make_context(
            backend=backend,
            progress_cb=self.progress_cb,
            chunk_rows=int(self.compute.chunk_rows),
        )

        manifest = pipeline.manifest
        result = PipelineRunResult(
            pipeline_id=ctx.pipeline_id,
            run_id=ctx.run_id,
            namespace=(manifest.namespace if manifest else "aqp"),
            name=(manifest.name if manifest else "ad-hoc"),
            backend=self.backend_label,
        )

        ctx.emit("plan", f"executor={self.backend_label} run_id={ctx.run_id}")

        started = time.perf_counter()
        try:
            pipeline.open_all(ctx)
            ctx.emit("materialize", f"streaming via {self.backend_label}")

            stream = pipeline.stream_through(ctx)
            sink_result = pipeline.sink.write(stream, ctx)
            result.sink_result = dict(sink_result or {})
            self._fold_sink_into_result(result, sink_result)
            ctx.lineage.update(result.lineage)
            ctx.emit(
                "done",
                f"finished in {time.perf_counter() - started:.2f}s "
                f"rows_written={result.total_rows_written}",
            )
            self._emit_executor_lineage(result=result, ctx=ctx, manifest=manifest)
        except Exception as exc:  # noqa: BLE001 - top-level catch
            logger.exception("pipeline execution failed: %s", exc)
            result.errors.append(f"execute_failed: {exc}")
            ctx.emit("error", f"execute_failed: {exc}")
            self._emit_executor_lineage(
                result=result,
                ctx=ctx,
                manifest=manifest,
                error=str(exc),
            )
        finally:
            pipeline.close_all(ctx)
            if backend is not None:
                try:
                    backend.shutdown()
                except Exception:  # noqa: BLE001
                    logger.debug("backend shutdown failed", exc_info=True)
            result.finished_at = datetime.utcnow()

        return result

    # ------------------------------------------------------------------
    # Hooks subclasses override
    # ------------------------------------------------------------------

    def _make_backend(self) -> ComputeBackend | None:
        from aqp.data.compute import LocalBackend

        return LocalBackend()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _emit_executor_lineage(
        *,
        result: PipelineRunResult,
        ctx: NodeContext,
        manifest: PipelineManifest | None,
        error: str | None = None,
    ) -> None:
        """Fire one ``materialize`` lineage event per sink-target table.

        Failures are swallowed so a busted lineage table never crashes
        a pipeline run. Targets are read from ``result.tables`` because
        the sink call already populated them with iceberg identifiers
        + row counts.
        """
        try:
            from aqp.data.catalog.lineage import LineageEvent, get_lineage_bus

            bus = get_lineage_bus()
            manifest_id = getattr(manifest, "id", None) if manifest else None
            actor = "executor.local"
            actor_kind = "service"
            base_summary = (
                f"executor={result.backend} run_id={ctx.run_id} "
                f"namespace={result.namespace} name={result.name}"
            )
            if not result.tables:
                bus.emit(
                    LineageEvent(
                        transform_kind="materialize",
                        target_table_id=None,
                        actor=actor,
                        actor_kind=actor_kind,
                        run_id=str(ctx.run_id),
                        manifest_id=str(manifest_id) if manifest_id else None,
                        service_name="data_engine",
                        rows_written=int(result.total_rows_written or 0),
                        summary=base_summary + (f" error={error}" if error else ""),
                        details={"error": error} if error else {},
                    )
                )
                return
            for table_entry in result.tables:
                target = getattr(table_entry, "iceberg_identifier", None) or getattr(
                    table_entry, "table_name", None
                )
                rows_written = int(getattr(table_entry, "rows_written", 0) or 0)
                bus.emit(
                    LineageEvent(
                        transform_kind="materialize",
                        target_table_id=str(target) if target else None,
                        actor=actor,
                        actor_kind=actor_kind,
                        run_id=str(ctx.run_id),
                        manifest_id=str(manifest_id) if manifest_id else None,
                        service_name="data_engine",
                        rows_written=rows_written,
                        summary=base_summary,
                        details={
                            "family": getattr(table_entry, "family", None),
                            "files_consumed": int(
                                getattr(table_entry, "files_consumed", 0) or 0
                            ),
                            "files_skipped": int(
                                getattr(table_entry, "files_skipped", 0) or 0
                            ),
                            "error": getattr(table_entry, "error", None) or error,
                        },
                    )
                )
        except Exception:  # noqa: BLE001
            logger.debug("executor lineage emit failed", exc_info=True)

    @staticmethod
    def _fold_sink_into_result(
        result: PipelineRunResult,
        sink_result: dict[str, Any] | None,
    ) -> None:
        if not sink_result:
            return
        # Sinks may report multiple tables (e.g. "tables" list mirroring
        # IngestionTableResult). Fold each into the unified report so
        # downstream UI doesn't need to special-case shapes.
        tables = sink_result.get("tables") or []
        for entry in tables:
            try:
                result.tables.append(_table_from_payload(entry))
            except Exception:  # noqa: BLE001
                logger.debug("malformed sink table entry: %r", entry)
        if not tables and "rows_written" in sink_result:
            # Single-table sink shape — synthesize one row.
            try:
                result.tables.append(
                    PipelineRunTable(
                        family=str(
                            sink_result.get("family")
                            or sink_result.get("name")
                            or "sink"
                        ),
                        iceberg_identifier=str(
                            sink_result.get("iceberg_identifier")
                            or sink_result.get("identifier")
                            or ""
                        ),
                        table_name=str(
                            sink_result.get("table_name")
                            or sink_result.get("name")
                            or "sink"
                        ),
                        rows_written=int(sink_result.get("rows_written") or 0),
                        files_consumed=int(sink_result.get("files_consumed") or 0),
                        files_skipped=int(sink_result.get("files_skipped") or 0),
                        truncated=bool(sink_result.get("truncated") or False),
                        annotation=sink_result.get("annotation"),
                        error=sink_result.get("error"),
                    )
                )
            except Exception:  # noqa: BLE001
                logger.debug("malformed sink result: %r", sink_result)
        if "lineage" in sink_result and isinstance(sink_result["lineage"], dict):
            result.lineage.update(sink_result["lineage"])
        if "extras" in sink_result and isinstance(sink_result["extras"], list):
            result.extras.extend(sink_result["extras"])


class LocalExecutor(Executor):
    """Single-process executor, default for laptops and unit tests."""

    backend_label = "local"

    def _make_backend(self) -> ComputeBackend | None:
        from aqp.data.compute import LocalBackend

        return LocalBackend()


class DaskExecutor(Executor):
    """Dask-Distributed executor.

    The executor itself runs in-process; the heavy lifting happens
    through the :class:`aqp.data.compute.dask.DaskBackend` instance,
    which lazily connects to ``compute.dask_address`` (or spins up a
    local cluster when no address is provided).
    """

    backend_label = "dask"

    def _make_backend(self) -> ComputeBackend | None:
        try:
            from aqp.data.compute import DaskBackend
        except Exception as exc:  # noqa: BLE001 - optional dep
            logger.warning("DaskBackend unavailable (%s); falling back to local", exc)
            from aqp.data.compute import LocalBackend

            return LocalBackend()
        return DaskBackend(
            address=self.compute.dask_address,
            n_workers=self.compute.n_workers,
            threads_per_worker=self.compute.threads_per_worker,
            extras=dict(self.compute.extras),
        )


class RayExecutor(Executor):
    """Ray executor.

    Backed by :class:`aqp.data.compute.ray.RayBackend`.
    """

    backend_label = "ray"

    def _make_backend(self) -> ComputeBackend | None:
        try:
            from aqp.data.compute import RayBackend
        except Exception as exc:  # noqa: BLE001 - optional dep
            logger.warning("RayBackend unavailable (%s); falling back to local", exc)
            from aqp.data.compute import LocalBackend

            return LocalBackend()
        return RayBackend(
            address=self.compute.ray_address,
            extras=dict(self.compute.extras),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_executor(
    spec_or_manifest: ComputeSpec | PipelineManifest,
    *,
    progress_cb: ProgressCallback | None = None,
) -> Executor:
    """Pick an executor flavor based on a manifest's ``compute`` block."""
    compute: ComputeSpec
    if isinstance(spec_or_manifest, PipelineManifest):
        compute = spec_or_manifest.compute
    else:
        compute = spec_or_manifest

    backend = compute.backend
    if backend == ComputeBackendKind.AUTO:
        # ``auto`` defaults to local; the actual auto-promotion logic
        # lives in :func:`aqp.data.compute.selection.pick_backend` and
        # is invoked by callers who want size-hint-driven promotion.
        backend = ComputeBackendKind.LOCAL

    if backend == ComputeBackendKind.DASK:
        return DaskExecutor(compute=compute, progress_cb=progress_cb)
    if backend == ComputeBackendKind.RAY:
        return RayExecutor(compute=compute, progress_cb=progress_cb)
    return LocalExecutor(compute=compute, progress_cb=progress_cb)


def _table_from_payload(payload: dict[str, Any]) -> PipelineRunTable:
    """Build a :class:`PipelineRunTable` from a sink result dict."""
    return PipelineRunTable(
        family=str(payload.get("family") or payload.get("name") or "table"),
        iceberg_identifier=str(payload.get("iceberg_identifier") or ""),
        table_name=str(payload.get("table_name") or payload.get("name") or ""),
        rows_written=int(payload.get("rows_written") or 0),
        files_consumed=int(payload.get("files_consumed") or 0),
        files_skipped=int(payload.get("files_skipped") or 0),
        truncated=bool(payload.get("truncated") or False),
        annotation=payload.get("annotation"),
        error=payload.get("error"),
        plan=payload.get("plan"),
        verifier=payload.get("verifier"),
        extras=dict(payload.get("extras") or {}),
    )


__all__ = [
    "DaskExecutor",
    "Executor",
    "LocalExecutor",
    "RayExecutor",
    "build_executor",
]
