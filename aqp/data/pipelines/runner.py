"""High-level orchestrator for the file → Iceberg ingestion flow.

The runner sequences:

1. ``discover_datasets`` — lays out candidate dataset families.
2. ``plan_ingestion`` (Nemotron Director) — refines the family layout
   into an :class:`IngestionPlan` with explicit namespaces, table
   names, and per-member skip lists.
3. ``materialize_dataset`` per planned table — streams rows into
   Iceberg.
4. ``verify_after_materialise`` (Director, optional) — when actual row
   counts come in below the planned floor (or every file is skipped),
   asks the LLM whether to accept or retry with adjusted knobs.
5. ``annotate_table`` — final LLM annotation pass for column docs +
   tags + domain.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aqp.config import settings
from aqp.data.pipelines.annotate import AnnotationResult, annotate_table
from aqp.data.pipelines.director import (
    IngestionPlan,
    PlannedDataset,
    plan_ingestion,
    verify_after_materialise,
)
from aqp.data.pipelines.discovery import DiscoveredDataset, discover_datasets
from aqp.data.pipelines.materialize import MaterializeResult, materialize_dataset

logger = logging.getLogger(__name__)


ProgressCallback = Callable[[str, str], None]


@dataclass
class IngestionTableResult:
    """Per-dataset outcome of an ingestion run."""

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
        }


@dataclass
class IngestionReport:
    """Top-level report returned by :class:`IngestionPipeline.run_path`."""

    source_path: str
    namespace: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    datasets_discovered: int = 0
    tables: list[IngestionTableResult] = field(default_factory=list)
    extras: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    director_plan: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "namespace": self.namespace,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "datasets_discovered": int(self.datasets_discovered),
            "tables": [t.to_dict() for t in self.tables],
            "extras": list(self.extras),
            "errors": list(self.errors),
            "director_plan": self.director_plan,
        }


class IngestionPipeline:
    """Discovery → director → materialize → verify → annotate orchestrator."""

    def __init__(
        self,
        *,
        progress_cb: ProgressCallback | None = None,
        max_rows_per_dataset: int | None = None,
        max_files_per_dataset: int | None = None,
        chunk_rows: int = 50_000,
        director_enabled: bool | None = None,
        allowed_namespaces: list[str] | None = None,
    ) -> None:
        self.progress_cb = progress_cb or (lambda phase, message: None)
        self.max_rows_per_dataset = max_rows_per_dataset
        self.max_files_per_dataset = max_files_per_dataset
        self.chunk_rows = int(chunk_rows)
        self.director_enabled = director_enabled
        self.allowed_namespaces = allowed_namespaces

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def run_path(
        self,
        path: Path | str,
        *,
        namespace: str | None = None,
        table_prefix: str | None = None,
        annotate: bool = True,
    ) -> IngestionReport:
        ns = (namespace or settings.iceberg_namespace_default or "aqp").strip() or "aqp"
        report = IngestionReport(source_path=str(Path(path).expanduser()), namespace=ns)
        try:
            self.progress_cb("discover", f"Walking {path}")
            datasets = discover_datasets(path)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"discovery_failed: {exc}")
            report.finished_at = datetime.utcnow()
            return report

        report.datasets_discovered = sum(1 for d in datasets if d.family != "__assets__")

        # Director plan (or identity fallback) ---------------------------
        plan = self._build_plan(
            datasets,
            source_path=report.source_path,
            namespace=ns,
        )
        report.director_plan = plan.to_dict()
        self._emit_plan_summary(plan)

        family_index = {d.family: d for d in datasets}

        # Surface __assets__ inventory through to the report extras list
        # so callers don't lose track of non-tabular files.
        for ds in datasets:
            if ds.family == "__assets__":
                report.extras.extend(ds.inventory_extra)

        for planned in plan.datasets:
            if not planned.include:
                continue
            ds = family_index.get(planned.family)
            if ds is None:
                report.errors.append(
                    f"plan_orphan[{planned.family}]: family missing from discovery"
                )
                continue

            table_result = self._materialise_with_verifier(
                ds,
                planned=planned,
                report=report,
                annotate_enabled=annotate,
            )
            report.tables.append(table_result)

        report.finished_at = datetime.utcnow()
        return report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_plan(
        self,
        datasets: list[DiscoveredDataset],
        *,
        source_path: str,
        namespace: str,
    ) -> IngestionPlan:
        if self.director_enabled is False:
            # Hard override; bypass the LLM but still emit an identity plan.
            from aqp.data.pipelines.director import _identity_plan  # type: ignore

            return _identity_plan(datasets, source_path=source_path, namespace=namespace)

        try:
            self.progress_cb(
                "plan",
                f"Director planning ingestion ({len(datasets)} families)",
            )
            return plan_ingestion(
                datasets,
                source_path=source_path,
                namespace=namespace,
                allowed_namespaces=self.allowed_namespaces,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("director planning failed: %s — using identity plan", exc)
            from aqp.data.pipelines.director import _identity_plan  # type: ignore

            plan = _identity_plan(
                datasets, source_path=source_path, namespace=namespace
            )
            plan.director_error = f"plan_call_failed: {exc}"
            return plan

    def _emit_plan_summary(self, plan: IngestionPlan) -> None:
        used = "director" if plan.director_used else "identity"
        msg = (
            f"plan ({used}): {len(plan.datasets)} table(s); "
            f"{len(plan.skipped_assets)} skipped"
        )
        self.progress_cb("plan", msg)
        if plan.director_error:
            self.progress_cb("plan", f"director_error: {plan.director_error}")

    def _run_materialise(
        self,
        ds: DiscoveredDataset,
        planned: PlannedDataset,
        *,
        max_rows_override: int | None,
        max_files_override: int | None,
    ) -> MaterializeResult:
        return materialize_dataset(
            ds,
            namespace=planned.target_namespace,
            target_namespace=planned.target_namespace,
            target_table=planned.target_table,
            member_filter=set(planned.member_paths) if planned.member_paths else None,
            max_rows_per_dataset=max_rows_override or self.max_rows_per_dataset,
            max_files_per_dataset=max_files_override or self.max_files_per_dataset,
            chunk_rows=self.chunk_rows,
        )

    def _materialise_with_verifier(
        self,
        ds: DiscoveredDataset,
        *,
        planned: PlannedDataset,
        report: IngestionReport,
        annotate_enabled: bool,
    ) -> IngestionTableResult:
        self.progress_cb(
            "materialize",
            f"Materializing {planned.iceberg_identifier} "
            f"(family={planned.family}, members={len(planned.member_paths)})",
        )
        try:
            mat = self._run_materialise(
                ds,
                planned,
                max_rows_override=None,
                max_files_override=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("materialize failed for %s", planned.family)
            report.errors.append(f"materialize_failed[{planned.family}]: {exc}")
            return IngestionTableResult(
                family=planned.family,
                iceberg_identifier=planned.iceberg_identifier,
                table_name=planned.target_table,
                error=str(exc),
                plan=planned.to_dict(),
            )

        verifier_payload: dict[str, Any] | None = None
        # Trigger the verifier when the run looks suspicious.
        floor = max(1, int(planned.expected_min_rows))
        rows_below_half = mat.rows_written < (floor * 0.5)
        every_file_skipped = mat.files_skipped > 0 and mat.files_consumed == 0
        if mat.error is None and (rows_below_half or every_file_skipped):
            self.progress_cb(
                "verify",
                f"Verifier checking {planned.iceberg_identifier} "
                f"(rows={mat.rows_written}, floor={floor}, "
                f"consumed={mat.files_consumed}, skipped={mat.files_skipped})",
            )
            try:
                verdict = verify_after_materialise(
                    planned=planned,
                    actual={
                        "rows_written": int(mat.rows_written),
                        "files_consumed": int(mat.files_consumed),
                        "files_skipped": int(mat.files_skipped),
                        "truncated": bool(mat.truncated),
                        "error": mat.error,
                    },
                    ingestion_settings={
                        "max_rows_per_dataset": int(
                            self.max_rows_per_dataset
                            or settings.iceberg_max_rows_per_dataset
                            or 0
                        ),
                        "max_files_per_dataset": int(
                            self.max_files_per_dataset
                            or settings.iceberg_max_files_per_dataset
                            or 0
                        ),
                        "chunk_rows": self.chunk_rows,
                    },
                )
                verifier_payload = verdict.to_dict()
                if verdict.verdict == "retry":
                    new_rows = verdict.retry_with.get("max_rows_per_dataset")
                    new_files = verdict.retry_with.get("max_files_per_dataset")
                    self.progress_cb(
                        "verify",
                        f"Verifier requested retry: {verdict.reason}",
                    )
                    try:
                        mat = self._run_materialise(
                            ds,
                            planned,
                            max_rows_override=int(new_rows) if new_rows else None,
                            max_files_override=int(new_files) if new_files else None,
                        )
                        verifier_payload["retry_outcome"] = {
                            "rows_written": int(mat.rows_written),
                            "files_consumed": int(mat.files_consumed),
                            "files_skipped": int(mat.files_skipped),
                            "truncated": bool(mat.truncated),
                            "error": mat.error,
                        }
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("verifier-retry materialize failed")
                        verifier_payload["retry_error"] = str(exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("verifier failed for %s: %s", planned.family, exc)
                verifier_payload = {"error": f"verifier_failed: {exc}"}

        entry = IngestionTableResult(
            family=planned.family,
            iceberg_identifier=mat.iceberg_identifier,
            table_name=mat.table_name,
            rows_written=mat.rows_written,
            files_consumed=mat.files_consumed,
            files_skipped=mat.files_skipped,
            truncated=mat.truncated,
            error=mat.error,
            plan=planned.to_dict(),
            verifier=verifier_payload,
        )

        if annotate_enabled and entry.error is None and entry.rows_written > 0:
            self.progress_cb("annotate", f"Annotating {mat.iceberg_identifier}")
            try:
                ann: AnnotationResult = annotate_table(
                    iceberg_identifier=mat.iceberg_identifier,
                    source_uri=str(report.source_path),
                    truncated=mat.truncated,
                    row_count=mat.rows_written,
                    extra_meta={
                        "family": planned.family,
                        "files_consumed": mat.files_consumed,
                        "files_skipped": mat.files_skipped,
                        "domain_hint": planned.domain_hint,
                        "director_notes": planned.notes,
                    },
                )
                entry.annotation = ann.to_dict()
            except Exception as exc:  # noqa: BLE001
                logger.warning("annotate failed for %s: %s", mat.iceberg_identifier, exc)
                entry.annotation = {"error": f"annotate_failed: {exc}"}

        return entry


def run_ingest_path(
    path: Path | str,
    *,
    namespace: str | None = None,
    table_prefix: str | None = None,
    annotate: bool = True,
    max_rows_per_dataset: int | None = None,
    max_files_per_dataset: int | None = None,
    progress_cb: ProgressCallback | None = None,
    director_enabled: bool | None = None,
    allowed_namespaces: list[str] | None = None,
) -> IngestionReport:
    """Convenience wrapper used by Celery tasks and the CLI harness."""
    pipe = IngestionPipeline(
        progress_cb=progress_cb,
        max_rows_per_dataset=max_rows_per_dataset,
        max_files_per_dataset=max_files_per_dataset,
        director_enabled=director_enabled,
        allowed_namespaces=allowed_namespaces,
    )
    return pipe.run_path(path, namespace=namespace, table_prefix=table_prefix, annotate=annotate)
