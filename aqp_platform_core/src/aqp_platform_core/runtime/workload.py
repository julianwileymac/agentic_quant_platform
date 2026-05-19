"""WorkloadRuntime — single sanctioned entry point for workload ops (AGENTS rule 45).

This is the shared runtime layer used by:

- The in-monolith routes ``aqp/api/routes/control_plane.py`` +
  ``aqp/api/routes/cluster_mgmt.py`` (embedded mode, talks directly to
  the active :class:`InfrastructureProvider` in-process).
- The micro-project ``aqp_control_plane/.../api/routers/deployments.py``
  (sidecar mode, talks to the active provider in its own process).

Both deployments share:

- The same :class:`aqp_platform_core.providers.InfrastructureProvider`
  ABC + auto-registering :class:`InfrastructureProviderMeta`.
- The same :class:`aqp_platform_core.models.workloads.WorkloadRun`
  audit ledger schema.
- The same kill-switch fan-out via :meth:`WorkloadRuntime.halt`.

The :class:`AuditSink` protocol lets each deployment plug in its own
persistence backend (structured logging + JSONL for ``aqp_cp``;
Postgres ``workload_runs`` table via the AQP ``LedgerWriter`` for the
in-monolith path). The runtime ALWAYS writes a row BEFORE dispatching
the provider call so a crash mid-call still leaves an audit trail.

AGENTS rule 4 — streamed actions (``exec`` / ``tail_logs``) yield
frames that the API layer reshapes into the canonical
``{task_id, stage, message, timestamp, **extras}`` payload before
pushing onto the WebSocket bus. The runtime itself does NOT publish to
Redis — that contract belongs to :mod:`aqp.tasks._progress`.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, runtime_checkable

from aqp_platform_core.models.config import ConfigMapPatch, ServiceConfig
from aqp_platform_core.models.deployment import DeploymentSpec, DeploymentStatus
from aqp_platform_core.models.workloads import (
    SecretRotationResult,
    WorkloadAction,
    WorkloadExecResult,
    WorkloadLogEvent,
    WorkloadRun,
    WorkloadRunStatus,
)
from aqp_platform_core.providers import (
    InfrastructureProvider,
    InfrastructureProviderError,
    InfrastructureProviderUnavailable,
    get_provider_registry,
)

logger = logging.getLogger(__name__)

ManagementMode = Literal["embedded", "sidecar"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WorkloadRuntimeError(RuntimeError):
    """Base class for runtime-side failures (not provider failures)."""


class WorkloadHaltedError(WorkloadRuntimeError):
    """Raised when an action is cancelled mid-flight by ``halt``."""

    def __init__(self, reason: str = "halted"):
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# AuditSink — pluggable persistence
# ---------------------------------------------------------------------------


@runtime_checkable
class AuditSink(Protocol):
    """Pluggable persistence backend for :class:`WorkloadRun` rows.

    Two production implementations:

    - :class:`LoggingAuditSink` (default) — structured log lines only.
      Suitable for unit tests and the sidecar micro-project's
      ``AQP_CP_AUDIT_BACKEND=jsonl`` path.
    - The AQP-side ``PostgresAuditSink`` (defined in
      ``aqp/persistence/models_workloads.py``) — writes through the
      :class:`aqp.persistence.ledger.LedgerWriter`.

    Implementations MUST be safe to call from async context (sync
    methods are fine; the runtime awaits them inside an executor when
    needed). They MUST NOT raise on persistence failure — log + carry on.
    """

    def start_run(self, run: WorkloadRun) -> None: ...

    def finish_run(self, run: WorkloadRun) -> None: ...


class LoggingAuditSink:
    """Default audit sink — structured log only, never persists.

    The micro-project augments this with a JSONL writer in
    ``aqp_cp.services.audit``. The AQP monolith replaces it entirely
    with a Postgres-backed sink. Both call ``start_run`` BEFORE the
    provider call and ``finish_run`` AFTER.
    """

    def __init__(self, *, logger_name: str = "aqp_platform_core.workload_runs") -> None:
        self._logger = logging.getLogger(logger_name)

    def start_run(self, run: WorkloadRun) -> None:  # noqa: D401
        try:
            body = run.model_dump(mode="json")
            self._logger.info(
                "workload_run phase=start %s", json.dumps(body, default=str)
            )
        except Exception:  # noqa: BLE001
            self._logger.warning("workload_run start log failed", exc_info=True)

    def finish_run(self, run: WorkloadRun) -> None:  # noqa: D401
        try:
            body = run.model_dump(mode="json")
            self._logger.info(
                "workload_run phase=finish %s", json.dumps(body, default=str)
            )
        except Exception:  # noqa: BLE001
            self._logger.warning("workload_run finish log failed", exc_info=True)


# ---------------------------------------------------------------------------
# RequestContext — user + tenancy carried into every run
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WorkloadRequestContext:
    """Tenancy + identity context propagated into ``WorkloadRun`` rows.

    Mirrors the shape of :class:`aqp.auth.context.RequestContext` so
    the in-monolith path can pass its own ``RequestContext`` directly;
    the micro-project converts its :class:`AuthenticatedUser` to one of
    these in :func:`aqp_cp.services.lifecycle.execute_with_audit`.
    """

    user_id: str
    org_id: str | None = None
    workspace_id: str | None = None
    experiment_id: str | None = None
    test_id: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Payload redaction — never persist secrets
# ---------------------------------------------------------------------------


_SECRET_HINTS = (
    "password",
    "secret",
    "token",
    "key",
    "credential",
    "private",
    "authorization",
    "kubeconfig",
    "client_secret",
    "api_token",
    "api_key",
    "jwt",
    "refresh_token",
    "access_token",
)


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort redaction of secret-looking keys.

    Applied by :class:`WorkloadRuntime` to every ``payload`` BEFORE
    persisting via the audit sink. The Management Engine subagent rule
    forbids credential printing in transcripts — this is the
    type-system-level enforcement of that policy.
    """
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        lk = str(key).lower()
        if any(hint in lk for hint in _SECRET_HINTS):
            redacted[key] = "<redacted>"
        elif isinstance(value, dict):
            redacted[key] = redact_payload(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_payload(v) if isinstance(v, dict) else v for v in value
            ]
        else:
            redacted[key] = value
    return redacted


def _safe_result_dict(result: Any) -> dict[str, Any]:
    """Normalise an arbitrary provider response to a JSON-friendly dict."""
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if isinstance(result, list):
        return {"count": len(result)}
    if isinstance(result, dict):
        return redact_payload(result)
    return {"value": str(result)}


def result_hash(result_dict: dict[str, Any]) -> str:
    """Deterministic SHA-256 of a normalised result for replay / audit."""
    blob = json.dumps(result_dict, default=str, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Halt registry — global kill-switch
# ---------------------------------------------------------------------------


class _HaltRegistry:
    """Process-wide registry of in-flight WorkloadRun ids + halt flags."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._inflight: dict[str, asyncio.Event] = {}
        self._global_halt_reason: str | None = None

    def register(self, run_id: str) -> asyncio.Event:
        event = asyncio.Event()
        with self._lock:
            self._inflight[run_id] = event
            if self._global_halt_reason is not None:
                event.set()
        return event

    def unregister(self, run_id: str) -> None:
        with self._lock:
            self._inflight.pop(run_id, None)

    def halt_all(self, reason: str = "kill-switch") -> int:
        with self._lock:
            self._global_halt_reason = reason
            for event in self._inflight.values():
                event.set()
            return len(self._inflight)

    def halt_one(self, run_id: str) -> bool:
        with self._lock:
            event = self._inflight.get(run_id)
            if event is None:
                return False
            event.set()
            return True

    def clear_global(self) -> None:
        """Test helper — reset the global halt flag so subsequent runs proceed."""
        with self._lock:
            self._global_halt_reason = None


_HALT = _HaltRegistry()


def get_halt_registry() -> _HaltRegistry:
    """Return the process-wide halt registry (test + halt-fan-out hook)."""
    return _HALT


# ---------------------------------------------------------------------------
# WorkloadRuntime
# ---------------------------------------------------------------------------


class WorkloadRuntime:
    """Single sanctioned entry point for runtime workload operations.

    Lifecycle for every action:

    1. Build a :class:`WorkloadRun` row in PENDING state with redacted payload.
    2. Register the run in the halt registry so ``halt`` can cancel it.
    3. Call :meth:`AuditSink.start_run` (BEFORE dispatch — survives crashes).
    4. Dispatch to the configured :class:`InfrastructureProvider`.
    5. On success: status=SUCCEEDED + normalised result + result_hash.
       On provider failure: status=FAILED + ``error`` populated.
       On halt: status=HALTED + ``halt_reason`` populated.
    6. Call :meth:`AuditSink.finish_run`.
    7. Return ``(WorkloadRun, provider_result)`` so the API layer can
       wrap the result in its envelope.

    Streamed actions (:meth:`tail_logs`) return an async generator that
    yields :class:`WorkloadLogEvent` frames AND writes the finish row
    when the generator is exhausted or closed. The API layer adapts
    these frames to the canonical AGENTS rule 4 progress shape.

    Construction:

    - ``provider_alias`` — registered alias on the
      :class:`aqp_platform_core.providers.ProviderRegistry`.
    - ``audit_sink`` — defaults to :class:`LoggingAuditSink`; production
      callers inject their Postgres-backed sink.
    - ``mode`` — ``"embedded"`` (default) calls the in-process provider;
      ``"sidecar"`` is a marker for the gateway proxy path (no behaviour
      change here; the proxy itself lives in ``aqp.api.proxy``).
    """

    def __init__(
        self,
        provider_alias: str,
        *,
        audit_sink: AuditSink | None = None,
        mode: ManagementMode = "embedded",
    ) -> None:
        self._provider_alias = provider_alias
        self._audit_sink: AuditSink = audit_sink or LoggingAuditSink()
        self._mode: ManagementMode = mode

    # --- Properties --------------------------------------------------

    @property
    def provider_alias(self) -> str:
        return self._provider_alias

    @property
    def mode(self) -> ManagementMode:
        return self._mode

    @property
    def audit_sink(self) -> AuditSink:
        return self._audit_sink

    def set_audit_sink(self, sink: AuditSink) -> None:
        """Swap the audit sink at runtime (mostly for tests + boot ordering)."""
        self._audit_sink = sink

    def get_provider(self) -> InfrastructureProvider:
        """Return the active provider instance."""
        return get_provider_registry().get_or_create(self._provider_alias)

    # --- Public action API ------------------------------------------

    async def start(
        self,
        spec: DeploymentSpec,
        *,
        ctx: WorkloadRequestContext,
    ) -> tuple[WorkloadRun, DeploymentStatus]:
        return await self._run(
            action=WorkloadAction.START,
            target=spec.service_id,
            namespace=spec.namespace,
            payload=spec.model_dump(mode="json"),
            ctx=ctx,
            fn=lambda p: p.start(spec),
        )

    async def stop(
        self,
        service_id: str,
        *,
        ctx: WorkloadRequestContext,
        namespace: str | None = None,
    ) -> tuple[WorkloadRun, DeploymentStatus]:
        return await self._run(
            action=WorkloadAction.STOP,
            target=service_id,
            namespace=namespace,
            payload={"namespace": namespace},
            ctx=ctx,
            fn=lambda p: p.stop(service_id, namespace=namespace),
        )

    async def scale(
        self,
        service_id: str,
        replicas: int,
        *,
        ctx: WorkloadRequestContext,
        namespace: str | None = None,
    ) -> tuple[WorkloadRun, DeploymentStatus]:
        return await self._run(
            action=WorkloadAction.SCALE,
            target=service_id,
            namespace=namespace,
            payload={"replicas": replicas, "namespace": namespace},
            ctx=ctx,
            fn=lambda p: p.scale(service_id, replicas, namespace=namespace),
        )

    async def restart(
        self,
        service_id: str,
        *,
        ctx: WorkloadRequestContext,
        namespace: str | None = None,
    ) -> tuple[WorkloadRun, DeploymentStatus]:
        return await self._run(
            action=WorkloadAction.RESTART,
            target=service_id,
            namespace=namespace,
            payload={"namespace": namespace},
            ctx=ctx,
            fn=lambda p: p.restart(service_id, namespace=namespace),
        )

    async def apply_config(
        self,
        patch: ConfigMapPatch,
        *,
        ctx: WorkloadRequestContext,
    ) -> tuple[WorkloadRun, bool]:
        return await self._run(
            action=WorkloadAction.APPLY_CONFIG,
            target=patch.service_id,
            namespace=None,
            payload=patch.model_dump(mode="json"),
            ctx=ctx,
            fn=lambda p: p.apply_config(patch),
        )

    async def exec(
        self,
        service_id: str,
        *,
        command: list[str],
        ctx: WorkloadRequestContext,
        container: str | None = None,
        timeout_seconds: int = 60,
        stdin: bytes | None = None,
        namespace: str | None = None,
    ) -> tuple[WorkloadRun, WorkloadExecResult]:
        return await self._run(
            action=WorkloadAction.EXEC,
            target=service_id,
            namespace=namespace,
            payload={
                "command": command,
                "container": container,
                "namespace": namespace,
                "timeout_seconds": timeout_seconds,
                "stdin_bytes": len(stdin) if stdin else 0,
            },
            ctx=ctx,
            fn=lambda p: p.exec(
                service_id,
                command=command,
                container=container,
                timeout_seconds=timeout_seconds,
                stdin=stdin,
                namespace=namespace,
            ),
        )

    async def rotate_secret(
        self,
        service_id: str,
        *,
        secret_name: str,
        ctx: WorkloadRequestContext,
        namespace: str | None = None,
    ) -> tuple[WorkloadRun, SecretRotationResult]:
        return await self._run(
            action=WorkloadAction.ROTATE_SECRET,
            target=service_id,
            namespace=namespace,
            payload={"secret_name": secret_name, "namespace": namespace},
            ctx=ctx,
            fn=lambda p: p.rotate_secret(
                service_id,
                secret_name=secret_name,
                namespace=namespace,
            ),
        )

    async def status(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        """Read-only — does NOT write a workload_runs row."""
        provider = self.get_provider()
        return await provider.status(service_id, namespace=namespace)

    async def list_deployments(
        self,
        *,
        namespace: str | None = None,
    ) -> list[DeploymentStatus]:
        """Read-only — does NOT write a workload_runs row."""
        provider = self.get_provider()
        return await provider.list_deployments(namespace=namespace)

    async def tail_logs(
        self,
        service_id: str,
        *,
        ctx: WorkloadRequestContext,
        container: str | None = None,
        since_seconds: int | None = None,
        tail: int | None = 200,
        follow: bool = False,
        max_lines: int | None = None,
        namespace: str | None = None,
    ) -> AsyncIterator[WorkloadLogEvent]:
        """Stream :class:`WorkloadLogEvent` frames; writes a single run row at completion.

        The run row is finalised when the generator is fully consumed
        or closed by the caller (the API layer's WebSocket disconnect).
        """
        run = self._build_run(
            action=WorkloadAction.LOGS,
            target=service_id,
            namespace=namespace,
            payload={
                "container": container,
                "since_seconds": since_seconds,
                "tail": tail,
                "follow": follow,
                "max_lines": max_lines,
                "namespace": namespace,
            },
            ctx=ctx,
        )
        halt_event = _HALT.register(run.run_id)
        self._safe_start(run)
        provider = self.get_provider()
        emitted = 0
        t0 = time.monotonic()
        try:
            async for event in provider.tail_logs(
                service_id,
                container=container,
                since_seconds=since_seconds,
                tail=tail,
                follow=follow,
                max_lines=max_lines,
                namespace=namespace,
            ):
                if halt_event.is_set():
                    raise WorkloadHaltedError("log stream halted")
                emitted += 1
                yield event
            self._safe_finish(
                run,
                status=WorkloadRunStatus.SUCCEEDED,
                result={"events_emitted": emitted},
            )
        except WorkloadHaltedError as exc:
            self._safe_finish(
                run,
                status=WorkloadRunStatus.HALTED,
                halt_reason=exc.reason,
                result={"events_emitted": emitted},
            )
            raise
        except InfrastructureProviderError as exc:
            self._safe_finish(
                run,
                status=WorkloadRunStatus.FAILED,
                error=str(exc),
                result={
                    "events_emitted": emitted,
                    "elapsed_ms": (time.monotonic() - t0) * 1000.0,
                },
            )
            raise
        except Exception as exc:  # noqa: BLE001
            self._safe_finish(
                run,
                status=WorkloadRunStatus.FAILED,
                error=str(exc),
                result={"events_emitted": emitted},
            )
            raise
        finally:
            _HALT.unregister(run.run_id)

    # --- Halt fan-out ------------------------------------------------

    def halt_all(self, reason: str = "kill-switch") -> int:
        """Halt every in-flight WorkloadRun on this process. Returns count halted."""
        return _HALT.halt_all(reason=reason)

    def halt_run(self, run_id: str) -> bool:
        """Halt a specific in-flight run by id."""
        return _HALT.halt_one(run_id)

    # --- Internals ---------------------------------------------------

    def _build_run(
        self,
        *,
        action: WorkloadAction,
        target: str,
        namespace: str | None,
        payload: dict[str, Any],
        ctx: WorkloadRequestContext,
    ) -> WorkloadRun:
        return WorkloadRun(
            run_id=str(uuid.uuid4()),
            started_at=datetime.now(timezone.utc),
            status=WorkloadRunStatus.PENDING,
            action=action,
            provider=self._provider_alias,
            target=target,
            namespace=namespace,
            user_id=ctx.user_id,
            request_id=ctx.request_id,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            experiment_id=ctx.experiment_id,
            test_id=ctx.test_id,
            payload=redact_payload(payload),
        )

    def _safe_start(self, run: WorkloadRun) -> None:
        try:
            self._audit_sink.start_run(run)
        except Exception:  # noqa: BLE001
            logger.warning(
                "audit sink start_run failed run_id=%s", run.run_id, exc_info=True
            )

    def _safe_finish(
        self,
        run: WorkloadRun,
        *,
        status: WorkloadRunStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        halt_reason: str | None = None,
    ) -> None:
        finished_at = datetime.now(timezone.utc)
        duration_ms = (finished_at - run.started_at).total_seconds() * 1000.0
        updated = run.model_copy(
            update={
                "status": status,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "result": result or {},
                "error": error,
                "halt_reason": halt_reason,
            }
        )
        try:
            self._audit_sink.finish_run(updated)
        except Exception:  # noqa: BLE001
            logger.warning(
                "audit sink finish_run failed run_id=%s", run.run_id, exc_info=True
            )

    async def _run(
        self,
        *,
        action: WorkloadAction,
        target: str,
        namespace: str | None,
        payload: dict[str, Any],
        ctx: WorkloadRequestContext,
        fn: Callable[[InfrastructureProvider], Awaitable[Any]],
    ) -> tuple[WorkloadRun, Any]:
        """Generic provider call wrapper with audit + halt support."""
        run = self._build_run(
            action=action,
            target=target,
            namespace=namespace,
            payload=payload,
            ctx=ctx,
        )
        halt_event = _HALT.register(run.run_id)
        self._safe_start(run)
        provider = self.get_provider()
        provider_task: asyncio.Task[Any] | None = None
        halt_task: asyncio.Task[Any] | None = None
        try:
            provider_task = asyncio.create_task(fn(provider))
            halt_task = asyncio.create_task(halt_event.wait())
            await asyncio.wait(
                {provider_task, halt_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if halt_event.is_set() and not provider_task.done():
                provider_task.cancel()
                try:
                    await provider_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
                self._safe_finish(
                    run,
                    status=WorkloadRunStatus.HALTED,
                    halt_reason="halt requested",
                )
                raise WorkloadHaltedError("halt requested")
            if not halt_task.done():
                halt_task.cancel()
            result = await provider_task
        except InfrastructureProviderUnavailable as exc:
            self._safe_finish(
                run,
                status=WorkloadRunStatus.FAILED,
                error=str(exc),
                result={"code": exc.code, "details": exc.details},
            )
            raise
        except InfrastructureProviderError as exc:
            self._safe_finish(
                run,
                status=WorkloadRunStatus.FAILED,
                error=str(exc),
                result={"code": exc.code, "details": exc.details},
            )
            raise
        except WorkloadHaltedError:
            raise
        except asyncio.CancelledError:
            self._safe_finish(
                run,
                status=WorkloadRunStatus.HALTED,
                halt_reason="cancelled",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            self._safe_finish(
                run,
                status=WorkloadRunStatus.FAILED,
                error=str(exc),
            )
            raise
        finally:
            _HALT.unregister(run.run_id)

        result_dict = _safe_result_dict(result)
        result_dict.setdefault("result_hash", result_hash(result_dict))
        self._safe_finish(
            run,
            status=WorkloadRunStatus.SUCCEEDED,
            result=result_dict,
        )
        return run, result


__all__ = [
    "AuditSink",
    "LoggingAuditSink",
    "ManagementMode",
    "WorkloadHaltedError",
    "WorkloadRequestContext",
    "WorkloadRuntime",
    "WorkloadRuntimeError",
    "get_halt_registry",
    "redact_payload",
    "result_hash",
]
