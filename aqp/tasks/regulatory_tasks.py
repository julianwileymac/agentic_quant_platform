"""Celery tasks for the third-order regulatory data sources.

Each task is a thin wrapper around the corresponding adapter — heavy
lifting (HTTP, Iceberg writes, Postgres upserts, lineage) lives in the
adapter modules under :mod:`aqp.data.sources.{cfpb,fda,uspto}`.

Progress + error reporting goes through the shared
:mod:`aqp.tasks._progress` bus so the existing WebSocket consumers in
the webui pick them up unchanged.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------- CFPB
@celery_app.task(bind=True, name="aqp.tasks.regulatory_tasks.ingest_cfpb_complaints")
def ingest_cfpb_complaints(
    self,
    company: str | None = None,
    product: str | None = None,
    date_received_min: str | None = None,
    date_received_max: str | None = None,
    has_narrative: bool | None = None,
    max_records: int | None = 5000,
    vt_symbol: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"CFPB complaints ingest company={company or '*'}")
    try:
        from aqp.data.sources.cfpb import CfpbComplaintsAdapter

        adapter = CfpbComplaintsAdapter()
        result = adapter.fetch_observations(
            company=company,
            product=product,
            date_received_min=date_received_min,
            date_received_max=date_received_max,
            has_narrative=has_narrative,
            max_records=max_records,
            vt_symbol=vt_symbol,
        )
        payload = {"rows": result.row_count, "lineage": result.lineage}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_cfpb_complaints failed")
        emit_error(task_id, str(exc))
        raise


# ---------------------------------------------------------------------- FDA
@celery_app.task(bind=True, name="aqp.tasks.regulatory_tasks.ingest_fda_applications")
def ingest_fda_applications(
    self,
    sponsor: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    endpoint: str = "drug/drugsfda.json",
    max_records: int | None = 5000,
    vt_symbol: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"FDA applications ingest sponsor={sponsor or '*'} endpoint={endpoint}")
    try:
        from aqp.data.sources.fda import FdaApplicationsAdapter

        result = FdaApplicationsAdapter().fetch_observations(
            sponsor=sponsor,
            date_min=date_min,
            date_max=date_max,
            endpoint=endpoint,
            max_records=max_records,
            vt_symbol=vt_symbol,
        )
        payload = {"rows": result.row_count, "lineage": result.lineage}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_fda_applications failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.regulatory_tasks.ingest_fda_adverse_events")
def ingest_fda_adverse_events(
    self,
    manufacturer: str | None = None,
    product: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    endpoint: str = "drug/event.json",
    max_records: int | None = 5000,
    vt_symbol: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"FDA adverse events ingest mfr={manufacturer or '*'}")
    try:
        from aqp.data.sources.fda import FdaAdverseEventsAdapter

        result = FdaAdverseEventsAdapter().fetch_observations(
            manufacturer=manufacturer,
            product=product,
            date_min=date_min,
            date_max=date_max,
            endpoint=endpoint,
            max_records=max_records,
            vt_symbol=vt_symbol,
        )
        payload = {"rows": result.row_count, "lineage": result.lineage}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_fda_adverse_events failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.regulatory_tasks.ingest_fda_recalls")
def ingest_fda_recalls(
    self,
    firm: str | None = None,
    classification: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    product_type: str = "drug",
    max_records: int | None = 5000,
    vt_symbol: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"FDA recalls ingest firm={firm or '*'} type={product_type}")
    try:
        from aqp.data.sources.fda import FdaRecallsAdapter

        result = FdaRecallsAdapter().fetch_observations(
            firm=firm,
            classification=classification,
            date_min=date_min,
            date_max=date_max,
            product_type=product_type,
            max_records=max_records,
            vt_symbol=vt_symbol,
        )
        payload = {"rows": result.row_count, "lineage": result.lineage}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_fda_recalls failed")
        emit_error(task_id, str(exc))
        raise


# ---------------------------------------------------------------------- USPTO
@celery_app.task(bind=True, name="aqp.tasks.regulatory_tasks.ingest_uspto_patents")
def ingest_uspto_patents(
    self,
    assignee: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    max_records: int | None = 5000,
    vt_symbol: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"USPTO patents ingest assignee={assignee or '*'}")
    try:
        from aqp.data.sources.uspto import UsptoPatentsAdapter

        result = UsptoPatentsAdapter().fetch_observations(
            assignee=assignee,
            date_min=date_min,
            date_max=date_max,
            max_records=max_records,
            vt_symbol=vt_symbol,
        )
        payload = {"rows": result.row_count, "lineage": result.lineage}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_uspto_patents failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.regulatory_tasks.ingest_uspto_trademarks")
def ingest_uspto_trademarks(
    self,
    serial_numbers: list[str] | None = None,
    vt_symbol: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"USPTO trademarks ingest n={len(serial_numbers or [])}")
    try:
        from aqp.data.sources.uspto import UsptoTrademarksAdapter

        result = UsptoTrademarksAdapter().fetch_observations(
            serial_numbers=serial_numbers,
            vt_symbol=vt_symbol,
        )
        payload = {"rows": result.row_count, "lineage": result.lineage}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_uspto_trademarks failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.regulatory_tasks.ingest_uspto_assignments")
def ingest_uspto_assignments(
    self,
    search_text: str = "",
    max_records: int | None = 5000,
    vt_symbol: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"USPTO assignments ingest q='{search_text}'")
    try:
        from aqp.data.sources.uspto import UsptoAssignmentsAdapter

        result = UsptoAssignmentsAdapter().fetch_observations(
            search_text=search_text or "*:*",
            max_records=max_records,
            vt_symbol=vt_symbol,
        )
        payload = {"rows": result.row_count, "lineage": result.lineage}
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("ingest_uspto_assignments failed")
        emit_error(task_id, str(exc))
        raise
