"""Pluggable progress emitter for long-running runtime operations.

This is the platform-core abstraction over the canonical AGENTS rule 4
progress frame::

    {"task_id": str, "stage": str, "message": str, "timestamp": float, **extras}

The frame shape is contract — every SSE / WebSocket consumer
(``aqp_client``, ``webui``, ``aqp_admin_ui``) reads it directly.

The protocol exists so that runtimes can be moved out of the AQP
monolith (e.g. :class:`TerraformRuntime` -> ``aqp_control_plane``
under the modified rule 42) without bringing their Redis pub/sub
dependency along. Two concrete emitters ship here:

- :class:`NullProgressEmitter` — swallows every frame. Default for
  unit tests and the slim CP image.
- :class:`StructuredLogProgressEmitter` — writes every frame to a
  structured logger. Default for the CP sidecar so operators can
  still tail progress via container logs even when the AQP-side
  Redis bus is unreachable.

The AQP monolith ships its own adapter (``aqp.tasks._progress``
backed by :mod:`aqp.ws.broker`) that satisfies this protocol — see
the broker shim in ``aqp/services/control_plane_progress_bridge.py``
(added alongside the Terraform relocation).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ProgressEmitter(Protocol):
    """Sink for AGENTS rule 4 progress frames.

    Implementations MUST NOT raise — long-running runtimes call
    :meth:`emit` from hot loops and rely on best-effort delivery.
    """

    def emit(
        self,
        task_id: str,
        stage: str,
        message: str,
        *,
        context: Any | None = None,
        **extra: Any,
    ) -> None:
        """Publish a single progress frame.

        ``context`` is a runtime-defined object (typically a
        :class:`aqp_platform_core.runtime.workload.WorkloadRequestContext`
        or :class:`RequestContext` from the monolith). Implementations
        SHOULD pull tenancy / FinOps tags off the context when
        possible but MUST tolerate ``None``.
        """

    def emit_done(
        self,
        task_id: str,
        result: Any,
        *,
        context: Any | None = None,
        **extra: Any,
    ) -> None:
        """Publish the terminal ``stage='done'`` frame for a task."""

    def emit_error(
        self,
        task_id: str,
        error: str,
        *,
        context: Any | None = None,
        **extra: Any,
    ) -> None:
        """Publish the terminal ``stage='error'`` frame for a task."""


class NullProgressEmitter:
    """No-op emitter for tests and slim deployments.

    Records the count of emitted frames so unit tests can assert
    on dispatch without exercising the Redis bus.
    """

    def __init__(self) -> None:
        self.emitted: int = 0

    def emit(
        self,
        task_id: str,
        stage: str,
        message: str,
        *,
        context: Any | None = None,
        **extra: Any,
    ) -> None:
        self.emitted += 1

    def emit_done(
        self,
        task_id: str,
        result: Any,
        *,
        context: Any | None = None,
        **extra: Any,
    ) -> None:
        self.emitted += 1

    def emit_error(
        self,
        task_id: str,
        error: str,
        *,
        context: Any | None = None,
        **extra: Any,
    ) -> None:
        self.emitted += 1


class StructuredLogProgressEmitter:
    """Emitter that writes the canonical frame to a structured logger.

    Useful when the runtime is running in the CP sidecar and the AQP
    Redis bus is unreachable — operators can still tail progress
    through container logs / Loki, and the frames are machine-parseable.
    """

    def __init__(
        self,
        *,
        logger_name: str = "aqp_platform_core.progress",
    ) -> None:
        self._logger = logging.getLogger(logger_name)

    def _frame(
        self,
        task_id: str,
        stage: str,
        message: str,
        context: Any | None,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        frame: dict[str, Any] = {
            "task_id": task_id,
            "stage": stage,
            "message": message,
            "timestamp": time.time(),
        }
        ctx_extras = _context_extras(context)
        if ctx_extras:
            frame["context"] = ctx_extras
        frame.update(extra)
        return frame

    def emit(
        self,
        task_id: str,
        stage: str,
        message: str,
        *,
        context: Any | None = None,
        **extra: Any,
    ) -> None:
        try:
            self._logger.info(
                "progress task_id=%s stage=%s message=%s extras=%s",
                task_id,
                stage,
                message,
                self._frame(task_id, stage, message, context, extra),
            )
        except Exception:  # noqa: BLE001
            # The contract forbids raising; degrade silently.
            logger.debug("progress emit failed", exc_info=True)

    def emit_done(
        self,
        task_id: str,
        result: Any,
        *,
        context: Any | None = None,
        **extra: Any,
    ) -> None:
        merged: dict[str, Any] = {"result": _safe_result(result)}
        merged.update(extra)
        self.emit(task_id, "done", "Task complete", context=context, **merged)

    def emit_error(
        self,
        task_id: str,
        error: str,
        *,
        context: Any | None = None,
        **extra: Any,
    ) -> None:
        self.emit(task_id, "error", error, context=context, **extra)


def _context_extras(ctx: Any | None) -> dict[str, str]:
    """Project a context object into FinOps-friendly extras.

    Best-effort + lazy — does not import :mod:`aqp.auth.context` so
    the platform-core boundary stays clean. Reads only public attrs.
    """
    if ctx is None:
        return {}
    if hasattr(ctx, "to_finops_extras"):
        try:
            value = ctx.to_finops_extras()
            if isinstance(value, dict):
                return {str(k): str(v) for k, v in value.items() if v}
        except Exception:  # noqa: BLE001
            pass
    out: dict[str, str] = {}
    for key in (
        "user_id",
        "org_id",
        "team_id",
        "workspace_id",
        "project_id",
        "lab_id",
        "run_id",
        "request_id",
        "experiment_id",
        "test_id",
    ):
        value = getattr(ctx, key, None)
        if value:
            out[key] = str(value)
    return out


def _safe_result(value: Any) -> Any:
    """Best-effort JSON-safe projection of an arbitrary result value."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except Exception:  # noqa: BLE001
            return str(value)
    if isinstance(value, dict):
        return {str(k): _safe_result(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_result(v) for v in value]
    return str(value)


__all__ = [
    "NullProgressEmitter",
    "ProgressEmitter",
    "StructuredLogProgressEmitter",
]
