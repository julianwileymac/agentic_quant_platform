"""WorkloadRun ledger schema (AGENTS rule 45).

This module is now a thin re-export of the shared schema in
:mod:`aqp_platform_core.models.workloads`. Both the in-monolith
:class:`aqp_platform_core.runtime.WorkloadRuntime` and the sidecar
:class:`aqp_cp` service write the same row shape so the SPA + Theia
desktop see one consistent ``workload_runs`` ledger regardless of
which deployment mode is active.

The ledger backend is pluggable — the default :class:`LoggingAuditSink`
plus the existing JSONL writer in :mod:`aqp_cp.services.audit` stay
the production sidecar implementation; the AQP monolith adds a
Postgres-backed sink via :mod:`aqp.persistence.models_workloads`.
"""
from __future__ import annotations

from aqp_platform_core.models.workloads import (
    WorkloadAction,
    WorkloadRun,
    WorkloadRunStatus,
)

__all__ = ["WorkloadAction", "WorkloadRun", "WorkloadRunStatus"]
