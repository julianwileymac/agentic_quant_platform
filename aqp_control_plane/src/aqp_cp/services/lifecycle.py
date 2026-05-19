"""Provider lookup + audit-wrapped orchestration of workload ops.

Phase A of the Management Engine moved the shared lifecycle logic into
:class:`aqp_platform_core.runtime.WorkloadRuntime`. This module now:

- Resolves the active :class:`InfrastructureProvider` via
  :func:`aqp_cp.providers.bootstrap` + the shared registry.
- Wraps the runtime in a thin :func:`execute_with_audit` helper that
  keeps the historical signature (so existing routers in
  ``aqp_cp/api/routers/*`` keep compiling) while delegating to
  :class:`WorkloadRuntime` under the hood.
- Plugs the existing :mod:`aqp_cp.services.audit` JSONL writer into
  the runtime via :class:`JsonlAuditSink`.

The in-monolith path (``aqp/api/routes/control_plane.py``) constructs
its own :class:`WorkloadRuntime` with a Postgres-backed audit sink and
does NOT import this module.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, status

from aqp_platform_core.models.workloads import (
    WorkloadAction,
    WorkloadRun,
    WorkloadRunStatus,
)
from aqp_platform_core.providers import (
    InfrastructureProvider,
    InfrastructureProviderError,
    InfrastructureProviderUnavailable,
)
from aqp_platform_core.runtime import (
    AuditSink,
    LoggingAuditSink,
    WorkloadHaltedError,
    WorkloadRuntime,
)
from aqp_platform_core.runtime.workload import WorkloadRequestContext

from aqp_cp.auth.deps import AuthenticatedUser
from aqp_cp.providers import (
    bootstrap,
    get_provider_registry,
)
from aqp_cp.services import audit as audit_service
from aqp_cp.settings import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit sink adapter — bridges WorkloadRuntime to aqp_cp.services.audit
# ---------------------------------------------------------------------------


class JsonlAuditSink(LoggingAuditSink):
    """Audit sink that ALSO appends to the configured JSONL file.

    The micro-project's default; production environments that want the
    Postgres ledger set ``AQP_CP_AUDIT_BACKEND=postgres`` (follow-up PR).
    """

    def start_run(self, run: WorkloadRun) -> None:  # noqa: D401
        super().start_run(run)
        try:
            audit_service._persist(run, phase="start")  # noqa: SLF001
        except Exception:  # noqa: BLE001
            logger.warning("JsonlAuditSink start_run failed", exc_info=True)

    def finish_run(self, run: WorkloadRun) -> None:  # noqa: D401
        super().finish_run(run)
        try:
            audit_service._persist(run, phase="finish")  # noqa: SLF001
        except Exception:  # noqa: BLE001
            logger.warning("JsonlAuditSink finish_run failed", exc_info=True)


# ---------------------------------------------------------------------------
# Runtime cache + provider resolution
# ---------------------------------------------------------------------------


_RUNTIME_CACHE: dict[str, WorkloadRuntime] = {}
_RUNTIME_LOCK = threading.RLock()


def get_active_provider(alias: str | None = None) -> InfrastructureProvider:
    """Return the configured :class:`InfrastructureProvider` instance.

    Defaults to ``settings.provider``; ``alias`` lets the operator
    override per-request (rare — primarily for the admin API).
    """
    bootstrap()  # idempotent
    settings = get_settings()
    chosen = alias or settings.provider
    try:
        return get_provider_registry().get_or_create(chosen)
    except InfrastructureProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": exc.code, "error_description": str(exc)},
        ) from exc


def get_workload_runtime(alias: str | None = None) -> WorkloadRuntime:
    """Return a cached :class:`WorkloadRuntime` for ``alias``.

    The runtime is keyed on alias so swapping providers (rare) gives
    each its own halt-aware execution path. The audit sink is the
    JSONL-augmented logger by default; replace via
    :meth:`WorkloadRuntime.set_audit_sink` from boot wiring.
    """
    bootstrap()
    settings = get_settings()
    chosen = alias or settings.provider
    with _RUNTIME_LOCK:
        if chosen not in _RUNTIME_CACHE:
            _RUNTIME_CACHE[chosen] = WorkloadRuntime(
                chosen,
                audit_sink=JsonlAuditSink(),
                mode="sidecar",
            )
        return _RUNTIME_CACHE[chosen]


def set_workload_runtime_audit_sink(sink: AuditSink) -> None:
    """Swap the audit sink for every cached runtime.

    Used by deployments that want to plug in a Postgres-backed sink at
    boot time (after the database engine is initialised).
    """
    with _RUNTIME_LOCK:
        for runtime in _RUNTIME_CACHE.values():
            runtime.set_audit_sink(sink)


# ---------------------------------------------------------------------------
# Backwards-compat shim — old function-style helper used by api/routers
# ---------------------------------------------------------------------------


async def execute_with_audit(
    *,
    action: WorkloadAction,
    target: str,
    user: AuthenticatedUser,
    payload: dict[str, Any] | None,
    fn: Callable[[], Awaitable[Any]],
    request_id: str | None = None,
    provider_alias: str | None = None,
) -> tuple[WorkloadRun, Any]:
    """Wrap a provider call with audit start + finish + structured errors.

    Backwards-compatible wrapper around :meth:`WorkloadRuntime._run`.
    New routers should construct a :class:`WorkloadRuntime` directly and
    call the typed action methods (:meth:`start`, :meth:`scale`, etc.).
    """
    settings = get_settings()
    prov_alias = provider_alias or settings.provider
    runtime = get_workload_runtime(prov_alias)
    ctx = WorkloadRequestContext(
        user_id=user.sub,
        org_id=user.org_id,
        workspace_id=user.workspace_id,
        request_id=request_id,
    )

    async def _wrapped(_provider) -> Any:  # noqa: ANN001
        return await fn()

    try:
        return await runtime._run(  # noqa: SLF001 - intentional bridge
            action=action,
            target=target,
            namespace=(payload or {}).get("namespace")
            if isinstance(payload, dict)
            else None,
            payload=payload or {},
            ctx=ctx,
            fn=_wrapped,
        )
    except InfrastructureProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": exc.code,
                "error_description": str(exc),
                "provider": exc.provider,
                "details": exc.details,
            },
        ) from exc
    except InfrastructureProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": exc.code,
                "error_description": str(exc),
                "provider": exc.provider,
                "details": exc.details,
            },
        ) from exc
    except WorkloadHaltedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "workload_halted",
                "error_description": exc.reason,
            },
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal", "error_description": str(exc)},
        ) from exc


__all__ = [
    "JsonlAuditSink",
    "execute_with_audit",
    "get_active_provider",
    "get_workload_runtime",
    "set_workload_runtime_audit_sink",
]
