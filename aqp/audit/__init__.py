"""Audit lake + transparency anchor subsystem (Phase 7).

Public surface:

- :func:`anchor_segment_tip` — push a sealed audit-segment tip-hash to
  the configured :class:`TransparencyAnchorSink`.
- :class:`TransparencyAnchorSink` — pluggable ABC; concrete sinks
  live in :mod:`aqp.audit.sinks` (``rekor`` / ``qldb`` / ``rfc3161``).
- :func:`replay_run` — re-execute a recorded agent / workflow / RL /
  analysis / backtest run against the hash-locked spec + MCP tool
  descriptor surface that existed at original run time.

Per RESTRUCTURING_PLAN.md §10 the audit lake composes with the Phase 6
per-cell MinIO + Object Lock COMPLIANCE policy. The hot write path
remains the Postgres ``audit_log`` hash chain (Alembic 0069 + 0079);
this package only adds the cold-storage + transparency anchor layer.
"""
from __future__ import annotations

from aqp.audit.protocol import (
    AnchorRecord,
    TransparencyAnchorSink,
    TRANSPARENCY_ANCHOR_SINK_KIND,
    list_transparency_anchor_sink_classes,
)

__all__ = [
    "AnchorRecord",
    "TRANSPARENCY_ANCHOR_SINK_KIND",
    "TransparencyAnchorSink",
    "list_transparency_anchor_sink_classes",
]
