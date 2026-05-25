"""Shared runtime layer used by both ``aqp/`` and ``aqp_control_plane``.

Exposes:

- :class:`WorkloadRuntime` (AGENTS rule 45) — single sanctioned
  entry point for runtime workload operations.
- :class:`ProgressEmitter` (AGENTS rule 4) — pluggable sink for
  the canonical ``{task_id, stage, message, timestamp, **extras}``
  frame shape. Enables runtimes to be relocated to the CP sidecar
  without bringing the AQP-side Redis bus along (see the modified
  rule 42 relocation of :class:`TerraformRuntime`).

Both the in-monolith routes and the sidecar micro-project import
the same classes.
"""
from __future__ import annotations

from aqp_platform_core.runtime.progress import (
    NullProgressEmitter,
    ProgressEmitter,
    StructuredLogProgressEmitter,
)
from aqp_platform_core.runtime.workload import (
    AuditSink,
    LoggingAuditSink,
    WorkloadHaltedError,
    WorkloadRuntime,
    WorkloadRuntimeError,
)

__all__ = [
    "AuditSink",
    "LoggingAuditSink",
    "NullProgressEmitter",
    "ProgressEmitter",
    "StructuredLogProgressEmitter",
    "WorkloadHaltedError",
    "WorkloadRuntime",
    "WorkloadRuntimeError",
]
