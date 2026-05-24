"""Transactional outbox for OpenLineage RunEvent relay (Workstream B).

The outbox pattern guarantees that lineage emission is transactionally
consistent with the data write: if the surrounding transaction aborts,
neither the data row nor the lineage event commits. A background
Celery beat task (:mod:`aqp.tasks.openlineage_relay_tasks`) drains
the outbox by POSTing each row's OpenLineage RunEvent payload to the
configured Marquez endpoint, then marks the row ``sent_at``.

Rows persist until they have been successfully relayed; a circuit
breaker in the relay task halts the drain at
``AQP_OPENLINEAGE_RELAY_BATCH`` events per pass so Marquez outages
don't blow up Postgres.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text

from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class OpenLineageOutbox(Base):
    """One row per pending or relayed OpenLineage RunEvent.

    ``payload`` is the verbatim JSON shape OpenLineage's HTTP transport
    expects. ``sent_at`` is set by the relay once Marquez has 2xx'd the
    POST; failed attempts increment ``attempts`` + record
    ``last_error`` so operators can inspect stuck rows without consulting
    the worker logs.
    """

    __tablename__ = "lineage_openlineage_outbox"

    id = Column(String(36), primary_key=True, default=_uuid)
    payload = Column(JSON, nullable=False)
    eventType = Column(String(32), nullable=False, index=True)  # START / COMPLETE / FAIL / ABORT
    job_namespace = Column(String(120), nullable=False, index=True)
    job_name = Column(String(240), nullable=False, index=True)
    run_id = Column(String(64), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    sent_at = Column(DateTime, nullable=True, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_lineage_openlineage_outbox_pending",
            "sent_at",
            "created_at",
        ),
    )


__all__ = ["OpenLineageOutbox"]
