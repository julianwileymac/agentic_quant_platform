"""``AnalysisRuntime`` — execute an :class:`AnalysisSpec` end-to-end.

Mirrors :class:`aqp.rl.runtime.RLRuntime` and
:class:`aqp.bots.runtime.BotRuntime`. One executor, one source of
truth for spec snapshotting + run ledger persistence + Iceberg writes.

Hard rule: every Celery task or REST handler that runs analysis must
go through this class — never call a flow runner directly. Telemetry,
``analysis_runs`` rows, ``analysis_step_results`` rows, and Iceberg
gold-tier persistence depend on the runtime owning the lifecycle.

Lifecycle for ``run(spec)``:

1. ``persist_spec(spec)`` snapshots into ``analysis_spec_versions``
   (idempotent by hash). The runtime keeps going if Postgres is
   unreachable so a developer laptop without a DB still works.
2. Open an ``analysis_runs`` row with ``status="running"``.
3. Resolve ``spec.dataset`` → :class:`pandas.DataFrame` via
   :func:`_load_dataset`.
4. For each :class:`AnalysisStep`, look up the
   :class:`FlowDescriptor` via :func:`resolve_flow`, validate its
   params, call the runner, persist a :class:`AnalysisStepResult`,
   and (when the flow returns an Arrow blob and ``persist=True``)
   append it to ``aqp_gold_analysis_<namespace>`` via
   :func:`aqp.data.iceberg_catalog.append_arrow`.
5. Finalise the ``analysis_runs`` row with status + summary.
6. Emit ``done`` / ``error`` on the progress bus when ``task_id`` is
   set so SSE consumers light up unchanged.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from aqp.analysis.base import FlowContext, FlowResult
from aqp.analysis.registry import persist_spec, resolve_flow
from aqp.analysis.spec import AnalysisSpec, AnalysisStep, BusinessMetadataRef, DatasetRef
from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StepOutcome:
    """Per-step record stitched into the final :class:`AnalysisRunResult`."""

    alias: str
    flow: str
    status: str  # completed | error | skipped
    metrics: dict[str, Any] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    chart: dict[str, Any] | None = None
    iceberg_identifier: str | None = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        return out


@dataclass
class AnalysisRunResult:
    """Outcome of a single :class:`AnalysisRuntime.run` call."""

    run_id: str
    spec_id: str | None
    version_id: str | None
    target: str  # run | preview
    status: str
    started_at: float
    duration_ms: float = 0.0
    task_id: str | None = None
    dataset_descriptor: str | None = None
    steps: list[StepOutcome] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "steps": [s.to_dict() for s in self.steps],
        }


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class AnalysisRuntime:
    """Sole sanctioned executor for an :class:`AnalysisSpec`.

    Construction is cheap; call :meth:`run` to drive the full lifecycle
    or :meth:`preview` to dispatch a single registered flow without
    persistence (the latter backs ``POST /analysis/flows/{flow}/preview``).
    """

    def __init__(
        self,
        spec: AnalysisSpec | None = None,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        context: Any | None = None,
    ) -> None:
        self.spec = spec
        self.run_id = run_id or str(uuid.uuid4())
        self.task_id = task_id
        if context is None:
            try:
                from aqp.auth.context import default_context  # type: ignore[attr-defined]

                context = default_context()
            except Exception:  # noqa: BLE001
                context = None
        self.context = context
        self._spec_id: str | None = None
        self._version_id: str | None = None
        self._db_run_id: str | None = None

    # --------------------------------------------------------- public API

    def run(self) -> AnalysisRunResult:
        """Execute :attr:`spec` end-to-end with full persistence."""
        if self.spec is None:
            raise ValueError("AnalysisRuntime.run requires a spec")
        return self._with_run(target="run", action=self._do_run)

    def preview(
        self,
        flow: str,
        df: Any,
        params: dict[str, Any],
        *,
        ctx_extras: dict[str, Any] | None = None,
    ) -> FlowResult:
        """One-shot preview of a single flow against an in-memory frame.

        Does NOT touch the run ledger or Iceberg — pure compute. Used
        by REST `/analysis/flows/{flow}/preview` and the lab's tabbed
        forms.
        """
        descriptor = resolve_flow(flow)
        params_obj = descriptor.params_model.model_validate(params or {})
        fctx = FlowContext(
            run_id=self.run_id,
            task_id=self.task_id,
            request_context=self.context,
            extras=dict(ctx_extras or {}),
        )
        result = descriptor.runner(df, params_obj, fctx)
        if result.flow != flow:  # be lenient: stamp if flow forgot
            result = result.model_copy(update={"flow": flow})
        return result

    # --------------------------------------------------------- core driver

    def _with_run(
        self, *, target: str, action
    ) -> AnalysisRunResult:
        assert self.spec is not None
        started = time.time()
        spec_id, version_id = self._snapshot_spec()
        run_db_id = self._open_run_row(target=target, version_id=version_id)
        self._db_run_id = run_db_id
        descriptor = self.spec.dataset.descriptor()
        self._emit_progress(
            "start",
            f"Analysis run {self.spec.name!r} (target={target})",
            run_db_id=run_db_id,
            target=target,
            spec_id=spec_id,
            version_id=version_id,
            dataset=descriptor,
        )
        steps: list[StepOutcome] = []
        status = "running"
        error: str | None = None
        try:
            steps = action()
            status = (
                "error"
                if any(s.status == "error" for s in steps)
                else "completed"
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("AnalysisRuntime.run failed for %s", self.spec.name)
            status = "error"
            error = str(exc)
            if self.task_id:
                emit_error(self.task_id, error, context=self.context)
        finally:
            self._finalise_run_row(
                run_db_id,
                status=status,
                steps=steps,
                error=error,
                dataset_descriptor=descriptor,
            )
        result = AnalysisRunResult(
            run_id=self.run_id,
            spec_id=spec_id,
            version_id=version_id,
            target=target,
            status=status,
            started_at=started,
            duration_ms=(time.time() - started) * 1000.0,
            task_id=self.task_id,
            dataset_descriptor=descriptor,
            steps=steps,
            error=error,
        )
        if status == "completed" and self.task_id:
            emit_done(self.task_id, result.to_dict(), context=self.context)
        return result

    def _do_run(self) -> list[StepOutcome]:
        assert self.spec is not None
        df = self._load_dataset(self.spec.dataset)
        upstream: dict[str, FlowResult] = {}
        outcomes: list[StepOutcome] = []
        for step in self.spec.steps:
            outcome = self._run_step(step, df, upstream)
            outcomes.append(outcome)
        return outcomes

    def _run_step(
        self,
        step: AnalysisStep,
        df: Any,
        upstream: dict[str, FlowResult],
    ) -> StepOutcome:
        assert self.spec is not None
        flow_name = step.flow_ref.flow
        started = time.time()
        try:
            descriptor = resolve_flow(flow_name)
        except KeyError as exc:
            self._emit_progress(
                "step:error",
                f"unknown flow {flow_name!r} for step {step.alias!r}",
                step=step.alias,
                flow=flow_name,
            )
            return StepOutcome(
                alias=step.alias,
                flow=flow_name,
                status="error",
                error=str(exc),
                duration_ms=(time.time() - started) * 1000.0,
            )

        try:
            params_obj = descriptor.params_model.model_validate(step.flow_ref.params)
        except Exception as exc:  # noqa: BLE001
            self._emit_progress(
                "step:error",
                f"params validation failed for {step.alias!r}: {exc}",
                step=step.alias,
                flow=flow_name,
            )
            return StepOutcome(
                alias=step.alias,
                flow=flow_name,
                status="error",
                error=str(exc),
                duration_ms=(time.time() - started) * 1000.0,
            )

        fctx = FlowContext(
            dataset_id=self.spec.dataset.descriptor(),
            run_id=self.run_id,
            task_id=self.task_id,
            request_context=self.context,
            upstream=dict(upstream),
        )
        self._emit_progress(
            "step:start",
            f"{step.alias} → {flow_name}",
            step=step.alias,
            flow=flow_name,
        )
        try:
            result = descriptor.runner(df, params_obj, fctx)
            if result.flow != flow_name:
                result = result.model_copy(update={"flow": flow_name})
        except Exception as exc:  # noqa: BLE001
            logger.exception("flow %s failed (step %s)", flow_name, step.alias)
            self._emit_progress(
                "step:error",
                f"{step.alias} failed: {exc}",
                step=step.alias,
                flow=flow_name,
            )
            self._record_step_result(
                step,
                flow_name=flow_name,
                params=step.flow_ref.params,
                metrics={},
                artifact_uri=None,
                status="error",
                error=str(exc),
                duration_ms=(time.time() - started) * 1000.0,
            )
            return StepOutcome(
                alias=step.alias,
                flow=flow_name,
                status="error",
                error=str(exc),
                duration_ms=(time.time() - started) * 1000.0,
            )

        iceberg_id = None
        if step.persist:
            iceberg_id = self._maybe_persist_arrow(
                step=step,
                descriptor=descriptor,
                result=result,
            )
        upstream[step.alias] = result

        duration_ms = (time.time() - started) * 1000.0
        self._emit_progress(
            "step:done",
            f"{step.alias} done",
            step=step.alias,
            flow=flow_name,
            iceberg_identifier=iceberg_id,
            duration_ms=duration_ms,
        )
        self._record_step_result(
            step,
            flow_name=flow_name,
            params=step.flow_ref.params,
            metrics=result.metrics,
            artifact_uri=iceberg_id,
            status="completed",
            error=None,
            duration_ms=duration_ms,
        )
        return StepOutcome(
            alias=step.alias,
            flow=flow_name,
            status="completed",
            metrics=dict(result.metrics or {}),
            rows=list(result.rows or []),
            artifacts=dict(result.artifacts or {}),
            chart=result.chart,
            iceberg_identifier=iceberg_id,
            duration_ms=duration_ms,
        )

    # ----------------------------------------------------- dataset loader

    def _load_dataset(self, ref: DatasetRef) -> Any:
        """Resolve :class:`DatasetRef` into a :class:`pandas.DataFrame`."""
        try:
            import pandas as pd  # noqa: F401
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("pandas is required to run analysis flows") from exc

        if ref.iceberg_identifier:
            return self._load_iceberg(ref)
        if ref.dataset_version_id:
            return self._load_dataset_version(ref)
        if ref.dataset_cfg:
            return self._load_inline_cfg(ref)
        raise ValueError("DatasetRef has no resolvable source")

    def _load_iceberg(self, ref: DatasetRef) -> Any:
        from aqp.data import iceberg_catalog

        identifier = ref.iceberg_identifier or ""
        columns = list(ref.columns) or None
        limit = int(ref.limit) if ref.limit else None
        try:
            arrow_table = iceberg_catalog.read_arrow(
                identifier,
                columns=columns,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Iceberg read failed for {identifier!r}: {exc}") from exc
        if arrow_table is None:
            raise RuntimeError(f"Iceberg table {identifier!r} not found")
        df = arrow_table.to_pandas()
        return self._apply_filters(df, ref)

    def _load_dataset_version(self, ref: DatasetRef) -> Any:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models import DatasetVersion
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "DB layer unavailable; cannot resolve dataset_version_id"
            ) from exc
        with SessionLocal() as session:
            row = session.get(DatasetVersion, ref.dataset_version_id)
            if row is None:
                raise RuntimeError(
                    f"DatasetVersion {ref.dataset_version_id!r} not found"
                )
            iceberg_id = (
                getattr(row, "iceberg_identifier", None)
                or (row.meta or {}).get("iceberg_identifier")
                if hasattr(row, "meta")
                else None
            )
        if not iceberg_id:
            raise RuntimeError(
                "DatasetVersion has no iceberg_identifier; cannot load"
            )
        proxy = ref.model_copy(update={"iceberg_identifier": iceberg_id})
        return self._load_iceberg(proxy)

    def _load_inline_cfg(self, ref: DatasetRef) -> Any:
        from aqp.core.registry import build_from_config

        try:
            handler = build_from_config(ref.dataset_cfg or {})
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"dataset_cfg build failed: {exc}") from exc
        if hasattr(handler, "fetch"):
            df = handler.fetch()
        elif hasattr(handler, "to_pandas"):
            df = handler.to_pandas()
        else:
            df = handler
        return self._apply_filters(df, ref)

    @staticmethod
    def _apply_filters(df: Any, ref: DatasetRef) -> Any:
        try:
            import pandas as pd
        except Exception:  # pragma: no cover
            return df
        if not isinstance(df, pd.DataFrame):
            return df
        out = df
        for col, value in (ref.filters or {}).items():
            if col in out.columns:
                if isinstance(value, list):
                    out = out[out[col].isin(value)]
                else:
                    out = out[out[col] == value]
        if ref.start and "timestamp" in out.columns:
            out = out[pd.to_datetime(out["timestamp"]) >= pd.to_datetime(ref.start)]
        if ref.end and "timestamp" in out.columns:
            out = out[pd.to_datetime(out["timestamp"]) <= pd.to_datetime(ref.end)]
        if ref.limit and len(out) > int(ref.limit):
            out = out.head(int(ref.limit))
        return out.reset_index(drop=True)

    # ----------------------------------------------------- iceberg persist

    def _maybe_persist_arrow(
        self,
        *,
        step: AnalysisStep,
        descriptor,
        result: FlowResult,
    ) -> str | None:
        if result.arrow_table is None:
            return result.iceberg_identifier
        assert self.spec is not None
        namespace = descriptor.iceberg_namespace()
        table_name = step.alias.replace("-", "_").replace(":", "_")
        identifier = f"{namespace}.{table_name}"
        try:
            from aqp.data import iceberg_catalog
            from aqp.data.catalog.active_metadata import (
                BusinessMetadata as ActiveMetadata,
            )

            biz = self._business_metadata_for_step(step, descriptor)
            iceberg_catalog.append_arrow(
                identifier,
                result.arrow_table,
                medallion_layer="gold",
                business_metadata=ActiveMetadata(**biz) if biz else None,
                actor=f"analysis_runtime:{self.spec.slug}",
                actor_kind="service",
                run_id=self.run_id,
                service_name="aqp.analysis.runtime",
                context=self.context,
            )
            result.iceberg_identifier = identifier
            return identifier
        except Exception:  # noqa: BLE001
            logger.warning(
                "iceberg persist failed for %s.%s; continuing without it",
                namespace,
                table_name,
                exc_info=True,
            )
            return None

    def _business_metadata_for_step(
        self,
        step: AnalysisStep,
        descriptor,
    ) -> dict[str, Any] | None:
        assert self.spec is not None
        biz = self.spec.business_metadata
        if biz is None:
            biz = BusinessMetadataRef(
                data_owner="analysis-runtime",
                semantic_definition=(
                    f"Output of analysis flow {descriptor.name} for spec {self.spec.slug}"
                ),
                domain=f"analysis.{descriptor.namespace}",
            )
        out = {
            "data_owner": biz.data_owner,
            "semantic_definition": biz.semantic_definition,
        }
        if biz.reliability_score is not None:
            out["reliability_score"] = float(biz.reliability_score)
        if biz.sla_class is not None:
            out["sla_class"] = str(biz.sla_class)
        if biz.domain is not None:
            out["domain"] = str(biz.domain)
        if biz.extras:
            out["extras"] = dict(biz.extras)
        return out

    # ----------------------------------------------------- DB plumbing

    def _snapshot_spec(self) -> tuple[str | None, str | None]:
        if self.spec is None:
            return None, None
        version_id = persist_spec(self.spec)
        spec_id = self._lookup_spec_id()
        self._spec_id = spec_id
        self._version_id = version_id
        return spec_id, version_id

    def _lookup_spec_id(self) -> str | None:
        if self.spec is None:
            return None
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_analysis import (
                AnalysisSpec as SpecRow,
            )

            with SessionLocal() as session:
                row = (
                    session.query(SpecRow)
                    .filter(SpecRow.slug == self.spec.slug)
                    .one_or_none()
                )
                return row.id if row is not None else None
        except Exception:  # pragma: no cover
            return None

    def _open_run_row(self, *, target: str, version_id: str | None) -> str | None:
        if self.spec is None:
            return None
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_analysis import AnalysisRun

            with SessionLocal() as session:
                row = AnalysisRun(
                    id=self.run_id,
                    spec_id=self._spec_id,
                    version_id=version_id,
                    target=target,
                    task_id=self.task_id,
                    status="running",
                    dataset_descriptor=self.spec.dataset.descriptor(),
                    started_at=datetime.utcnow(),
                )
                self._stamp_tenancy(row)
                session.add(row)
                session.commit()
                return row.id
        except Exception:  # pragma: no cover
            logger.debug("Could not open analysis_runs row", exc_info=True)
            return None

    def _finalise_run_row(
        self,
        run_db_id: str | None,
        *,
        status: str,
        steps: list[StepOutcome],
        error: str | None,
        dataset_descriptor: str | None,
    ) -> None:
        if run_db_id is None:
            return
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_analysis import AnalysisRun

            with SessionLocal() as session:
                row = session.get(AnalysisRun, run_db_id)
                if row is None:
                    return
                row.status = status
                row.error = error
                row.dataset_descriptor = dataset_descriptor
                row.ended_at = datetime.utcnow()
                row.result_summary = {
                    "n_steps": len(steps),
                    "n_completed": sum(1 for s in steps if s.status == "completed"),
                    "n_error": sum(1 for s in steps if s.status == "error"),
                    "iceberg_identifiers": [
                        s.iceberg_identifier for s in steps if s.iceberg_identifier
                    ],
                }
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not finalise analysis_runs row", exc_info=True)

    def _record_step_result(
        self,
        step: AnalysisStep,
        *,
        flow_name: str,
        params: dict[str, Any],
        metrics: dict[str, Any],
        artifact_uri: str | None,
        status: str,
        error: str | None,
        duration_ms: float,
    ) -> None:
        if self._db_run_id is None:
            return
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_analysis import AnalysisStepResult

            with SessionLocal() as session:
                row = AnalysisStepResult(
                    run_id=self._db_run_id,
                    step_alias=step.alias,
                    flow=flow_name,
                    status=status,
                    params_json=dict(params or {}),
                    metrics_json=dict(metrics or {}),
                    artifact_uri=artifact_uri,
                    duration_ms=float(duration_ms),
                    error=error,
                    created_at=datetime.utcnow(),
                )
                self._stamp_tenancy(row)
                session.add(row)
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not record analysis_step_result", exc_info=True)

    def _stamp_tenancy(self, row: Any) -> None:
        ctx = self.context
        if ctx is None:
            return
        for attr_ctx, attr_row in (
            ("user_id", "owner_user_id"),
            ("workspace_id", "workspace_id"),
            ("project_id", "project_id"),
        ):
            value = getattr(ctx, attr_ctx, None)
            if value and hasattr(row, attr_row) and getattr(row, attr_row, None) in (
                None,
                "",
            ):
                setattr(row, attr_row, value)

    # ----------------------------------------------------- progress

    def _emit_progress(self, stage: str, message: str, **extra: Any) -> None:
        slug = self.spec.slug if self.spec else "ad_hoc"
        logger.info("[analysis:%s] %s: %s", slug, stage, message)
        if not self.task_id:
            return
        emit(
            self.task_id,
            stage,
            message,
            context=self.context,
            run_id=self.run_id,
            spec_slug=slug,
            **extra,
        )


def runtime_for(spec_or_name: Any, **kwargs: Any) -> AnalysisRuntime:
    """Build a runtime from an :class:`AnalysisSpec` instance or a slug."""
    if isinstance(spec_or_name, AnalysisSpec):
        spec = spec_or_name
    else:
        from aqp.analysis.registry import get_analysis_spec

        spec = get_analysis_spec(str(spec_or_name))
    return AnalysisRuntime(spec, **kwargs)


__all__ = [
    "AnalysisRunResult",
    "AnalysisRuntime",
    "StepOutcome",
    "runtime_for",
]
