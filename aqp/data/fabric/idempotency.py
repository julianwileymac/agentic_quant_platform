from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from aqp.data.fabric.identity import FabricHashMixin
from aqp.observability.fabric_bus import get_observability_bus
from aqp.persistence.db import get_session
from aqp.persistence.models_ingestion_ledger import IngestionLedgerRow

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"SUCCESS", "PARTIAL_FAILURE", "FATAL_ERROR"})


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _coerce_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return {str(key): value[key] for key in sorted(value.keys(), key=str)}


def compute_request_hash(
    *,
    data_source_id: str,
    edge_ids: Sequence[str],
    time_window: tuple[datetime, datetime] | None = None,
    extras: dict[str, Any] | None = None,
) -> str:
    """Compute a deterministic request hash for feed sync calls."""
    normalized_window: tuple[str, str] | None = None
    if time_window is not None:
        normalized_window = (_iso_utc(time_window[0]), _iso_utc(time_window[1]))
    payload: dict[str, Any] = {
        "data_source_id": str(data_source_id),
        "edge_ids": sorted(str(edge_id) for edge_id in edge_ids),
        "time_window": normalized_window,
        "extras": _coerce_mapping(extras),
    }
    return FabricHashMixin.compute_dict_hash(payload)


def check_or_insert_pending(
    *,
    data_source_id: str,
    request_hash: str,
    requested_time_window: str | None,
    fabric_uuid: str | None = None,
    business_metadata: dict[str, Any] | None = None,
    otel_trace_id: str | None = None,
    otel_span_id: str | None = None,
    session: Any | None = None,
) -> tuple[str | None, bool]:
    """Idempotency gate for ingestion runs.

    Returns ``(existing_ledger_id, is_skip)``:
    - ``is_skip=True`` when a SUCCESS row with this request hash exists.
    - ``is_skip=False`` with a freshly inserted PENDING row id otherwise.
    """

    def _run(active_session: Any, *, should_commit: bool) -> tuple[str | None, bool]:
        existing = (
            active_session.query(IngestionLedgerRow)
            .filter(
                IngestionLedgerRow.request_hash == request_hash,
                IngestionLedgerRow.execution_status == "SUCCESS",
            )
            .order_by(IngestionLedgerRow.execution_start.desc())
            .first()
        )
        if existing is not None:
            bus = get_observability_bus()
            bus.hash_collisions.add(
                1,
                attributes={
                    "data_source_id": str(data_source_id),
                    "request_hash": str(request_hash),
                },
            )
            logger.info(
                "Idempotency hit: request_hash=%s data_source_id=%s existing_ledger_id=%s",
                request_hash,
                data_source_id,
                existing.id,
            )
            return str(existing.id), True

        row = IngestionLedgerRow(
            fabric_uuid=fabric_uuid or str(uuid.uuid4()),
            data_source_id=str(data_source_id),
            request_hash=str(request_hash),
            requested_time_window=requested_time_window,
            execution_start=datetime.utcnow(),
            records_extracted=0,
            records_persisted=0,
            execution_status="PENDING",
            business_metadata=dict(business_metadata or {}),
            otel_trace_id=otel_trace_id,
            otel_span_id=otel_span_id,
        )
        active_session.add(row)
        active_session.flush()
        if should_commit:
            active_session.commit()
        return str(row.id), False

    if session is not None:
        try:
            return _run(session, should_commit=True)
        except Exception as exc:  # noqa: BLE001
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
            logger.warning(
                "Idempotency DB check unavailable; proceeding with best effort (%s)",
                exc,
            )
            return None, False

    try:
        with get_session() as active_session:
            return _run(active_session, should_commit=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Idempotency DB check unavailable; proceeding with best effort (%s)",
            exc,
        )
        return None, False


def update_ledger_status(
    ledger_id: str,
    *,
    status: str,
    records_extracted: int | None = None,
    records_persisted: int | None = None,
    error_traceback: str | None = None,
    lineage_snapshot: dict[str, Any] | None = None,
    fetcher_run_id: str | None = None,
    session: Any | None = None,
) -> None:
    """Update an existing ingestion-ledger row in place."""

    def _run(active_session: Any, *, should_commit: bool) -> None:
        row = (
            active_session.query(IngestionLedgerRow)
            .filter(IngestionLedgerRow.id == str(ledger_id))
            .first()
        )
        if row is None:
            logger.warning("Ledger row not found for status update: %s", ledger_id)
            return

        row.execution_status = status
        if records_extracted is not None:
            row.records_extracted = max(0, int(records_extracted))
        if records_persisted is not None:
            row.records_persisted = max(0, int(records_persisted))
        if error_traceback is not None:
            row.error_traceback = error_traceback
        if lineage_snapshot is not None:
            row.lineage_snapshot = dict(lineage_snapshot)
        if fetcher_run_id is not None:
            row.fetcher_run_id = str(fetcher_run_id)
        if status in _TERMINAL_STATUSES:
            row.execution_end = datetime.utcnow()

        active_session.add(row)
        active_session.flush()
        if should_commit:
            active_session.commit()

    if session is not None:
        try:
            _run(session, should_commit=True)
            return
        except Exception as exc:  # noqa: BLE001
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
            logger.warning("Failed to update ingestion ledger %s: %s", ledger_id, exc)
            return

    try:
        with get_session() as active_session:
            _run(active_session, should_commit=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to update ingestion ledger %s: %s", ledger_id, exc)


__all__ = [
    "check_or_insert_pending",
    "compute_request_hash",
    "update_ledger_status",
]
