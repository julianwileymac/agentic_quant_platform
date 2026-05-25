"""Admin audit ledger — audit-first writes for every mutating route.

Mirrors the ``WorkloadRun`` audit shape from
:mod:`aqp_platform_core.runtime.workload`. Two sinks ship:

- :class:`JsonlAdminAuditSink` — appends to a JSONL file (local dev,
  CI). Always available.
- :class:`HttpAdminAuditSink` — POSTs every row to the AQP monolith
  ``/_internal/audit/admin-runs`` endpoint using the platform-core
  M2M broker (Entra-primary). Selected when
  ``AQP_ADMIN_AUDIT_SINK=http``.

Every mutating admin route writes ``status=pending`` BEFORE the
action and ``status=succeeded|failed|halted`` AFTER. The pattern
guarantees the audit trail survives mid-call crashes.
"""
from __future__ import annotations

from aqp_admin.audit.sink import (
    AdminAuditSink,
    AdminAuditEvent,
    HttpAdminAuditSink,
    JsonlAdminAuditSink,
    LoggingAdminAuditSink,
    build_default_audit_sink,
)

__all__ = [
    "AdminAuditEvent",
    "AdminAuditSink",
    "HttpAdminAuditSink",
    "JsonlAdminAuditSink",
    "LoggingAdminAuditSink",
    "build_default_audit_sink",
]
