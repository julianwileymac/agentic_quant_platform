"""Shared runtime layer used by both ``aqp/`` and ``aqp_control_plane``.

Currently exposes :class:`WorkloadRuntime` (AGENTS rule 45) — the single
sanctioned entry point for runtime workload operations. Mirrors the
spec-runtime pattern of :class:`aqp.terraform.runtime.TerraformRuntime`
and :class:`aqp.agents.runtime.AgentRuntime`.

The runtime is intentionally provider-agnostic: it takes a
:class:`aqp_platform_core.providers.InfrastructureProvider` alias and a
pluggable :class:`AuditSink` and orchestrates the action lifecycle
(start row -> dispatch -> finish row). Both the in-monolith routes and
the sidecar micro-project import the same class.
"""
from __future__ import annotations

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
    "WorkloadHaltedError",
    "WorkloadRuntime",
    "WorkloadRuntimeError",
]
