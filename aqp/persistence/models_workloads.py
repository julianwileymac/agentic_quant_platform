"""Postgres ledger for the AQP Management Engine (AGENTS rule 45).

The `workload_runs` table is the Postgres backing of the shared
:class:`aqp_platform_core.models.workloads.WorkloadRun` wire-format
row. The in-monolith :class:`aqp_platform_core.runtime.WorkloadRuntime`
plugs a :class:`PostgresWorkloadAuditSink` into the runtime at boot
time; the micro-project sidecar keeps its JSONL writer
(``aqp_cp.services.lifecycle.JsonlAuditSink``).

The table carries the full AGENTS rule 34 stamping (``experiment_id``
+ ``test_id`` FKs) so workload operations show up in the
``experiments`` / ``tests`` umbrella in the same way as
``terraform_runs`` and ``workflow_runs``.

Adding this table is strictly additive — Alembic 0055 creates it. The
ORM definition stays the source of truth for the column set; the
migration mirrors it. Per AGENTS rule 6 the migration is immutable
once shipped.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from aqp.persistence.models import Base

from aqp_platform_core.models.workloads import (
    WorkloadAction,
    WorkloadRun,
    WorkloadRunStatus,
)
from aqp_platform_core.runtime import AuditSink

logger = logging.getLogger(__name__)


_JSONB_COMPAT = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class WorkloadRunRow(Base):
    """Postgres mirror of :class:`WorkloadRun` (AGENTS rule 45).

    Not tenant-scoped via the standard mixins — workload ops can target
    cross-org infrastructure and the user/org claim comes from the JWT
    payload, not the resource graph. ``organization_id`` /
    ``workspace_id`` are nullable FKs onto the tenancy tables for
    audit / dashboard filtering.
    """

    __tablename__ = "workload_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    run_uid = Column(String(36), nullable=False, unique=True, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    action = Column(String(24), nullable=False, index=True)
    provider_alias = Column(String(80), nullable=False, index=True)
    target = Column(String(240), nullable=False, index=True)
    namespace = Column(String(120), nullable=True, index=True)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id = Column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    experiment_id = Column(
        String(36),
        ForeignKey("aqp_experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    test_id = Column(
        String(36),
        ForeignKey("aqp_tests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_id = Column(String(120), nullable=True, index=True)
    payload = Column(_JSONB_COMPAT, nullable=False, default=dict)
    result = Column(_JSONB_COMPAT, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    halt_reason = Column(String(120), nullable=True)
    duration_ms = Column(Float, nullable=True)


Index(
    "ix_workload_runs_status_started_desc",
    WorkloadRunRow.status,
    WorkloadRunRow.started_at.desc(),
)
Index(
    "ix_workload_runs_action_started_desc",
    WorkloadRunRow.action,
    WorkloadRunRow.started_at.desc(),
)
Index(
    "ix_workload_runs_provider_target",
    WorkloadRunRow.provider_alias,
    WorkloadRunRow.target,
)


# ---------------------------------------------------------------------------
# AuditSink adapter — writes through SQLAlchemy
# ---------------------------------------------------------------------------


class PostgresWorkloadAuditSink:
    """Audit sink that persists :class:`WorkloadRun` rows to Postgres.

    The in-monolith :func:`aqp.api.routes.control_plane.build_workload_runtime`
    injects this into :class:`WorkloadRuntime` at boot time. The sink
    NEVER raises on persistence failure — the runtime's halt + retry
    semantics rely on best-effort audit writes, and we already
    structured-log the row via the parent :class:`LoggingAuditSink`
    pattern.

    The sink is intentionally NOT a subclass of
    :class:`aqp_platform_core.runtime.LoggingAuditSink` — duck-typed
    against the :class:`AuditSink` :class:`Protocol`. This keeps the
    AQP-side import cost low (no extra logging configuration) and lets
    operators chain it with their own logger sink if they want both.
    """

    def __init__(self, session_factory: Any) -> None:
        """``session_factory`` is a ``sessionmaker`` (sync) — call ``()`` to get a session."""
        self._session_factory = session_factory

    # AuditSink protocol ----------------------------------------------

    def start_run(self, run: WorkloadRun) -> None:
        self._upsert(run)

    def finish_run(self, run: WorkloadRun) -> None:
        self._upsert(run)

    # Internals -------------------------------------------------------

    def _upsert(self, run: WorkloadRun) -> None:
        try:
            session = self._session_factory()
        except Exception:  # noqa: BLE001
            logger.warning(
                "workload_runs sink could not acquire DB session run_id=%s",
                run.run_id,
                exc_info=True,
            )
            return
        try:
            existing = (
                session.query(WorkloadRunRow)
                .filter(WorkloadRunRow.run_uid == run.run_id)
                .one_or_none()
            )
            payload = self._to_columns(run)
            if existing is None:
                row = WorkloadRunRow(
                    id=str(uuid.uuid4()),
                    run_uid=run.run_id,
                    **payload,
                )
                session.add(row)
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)
            session.commit()
        except Exception:  # noqa: BLE001
            logger.warning(
                "workload_runs sink upsert failed run_id=%s", run.run_id, exc_info=True
            )
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass

    def _to_columns(self, run: WorkloadRun) -> dict[str, Any]:
        return {
            "started_at": run.started_at or datetime.now(timezone.utc),
            "finished_at": run.finished_at,
            "status": str(run.status.value if isinstance(run.status, WorkloadRunStatus) else run.status),
            "action": str(run.action.value if isinstance(run.action, WorkloadAction) else run.action),
            "provider_alias": run.provider,
            "target": run.target,
            "namespace": run.namespace,
            "user_id": run.user_id,
            "organization_id": run.org_id,
            "workspace_id": run.workspace_id,
            "experiment_id": run.experiment_id,
            "test_id": run.test_id,
            "request_id": run.request_id,
            "payload": run.payload,
            "result": run.result,
            "error": run.error,
            "halt_reason": run.halt_reason,
            "duration_ms": run.duration_ms,
        }


# Runtime check — duck-typed at boot time, asserted statically here.
assert isinstance(PostgresWorkloadAuditSink, type)  # mypy hint, no-op
_ = AuditSink  # re-export hint


__all__ = ["PostgresWorkloadAuditSink", "WorkloadRunRow"]
