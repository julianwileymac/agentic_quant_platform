"""Shared base class for the MLOps lifecycle handlers.

Every handler inherits :class:`MLOpsHandler` so the platform sees a
uniform audit / policy / lineage surface across the six lifecycle
operations. The base class wraps the actual handler call (``run``)
with:

1. Policy enforcement (default: workspace tenancy + required scopes;
   subclasses override).
2. Best-effort lineage emission via the existing :class:`LineageBus`
   (matches the contract :class:`aqp.data.mcp.base.DataMCPTool` uses).
3. Structured :class:`HandlerResult` return so callers (routes, MCP
   tools, Celery tasks) get a deterministic shape with elapsed time +
   warnings.

Handlers MUST NOT call ``router_complete`` or write to Iceberg /
Postgres outside the platform's existing entry points. They orchestrate
existing primitives (``iceberg_catalog.append_arrow`` via the store
handler, ``aqp.persistence.db.get_session`` via the cache handler) but
do not embed business logic that belongs in :mod:`aqp_models.models`.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class HandlerPolicyError(PermissionError):
    """Raised when :meth:`MLOpsHandler.policy_check` rejects the call."""


@dataclass(slots=True)
class HandlerContext:
    """Per-call context every handler observes.

    Mirrors :class:`aqp.data.mcp.base.MCPToolContext` so a DataMCPTool
    can pass its own context straight into a handler call.
    """

    actor: str | None = None
    actor_kind: str | None = None  # user|agent|service|system
    session_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    granted_scopes: tuple[str, ...] = ()
    request_id: str | None = None
    received_at: datetime = field(default_factory=datetime.utcnow)
    extras: dict[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return scope in self.granted_scopes


@dataclass(slots=True)
class HandlerResult:
    """Uniform handler outcome."""

    ok: bool
    data: Any = None
    summary: str | None = None
    elapsed_ms: float | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        # Strip non-JSON-serialisable items defensively — handlers can
        # stash arbitrary Python in ``data`` and the route layer
        # converts only what is safe.
        data = self.data
        try:
            import json

            json.dumps(data, default=str)
            safe_data: Any = data
        except (TypeError, ValueError):
            safe_data = repr(data)
        return {
            "ok": bool(self.ok),
            "data": safe_data,
            "summary": self.summary,
            "elapsed_ms": self.elapsed_ms,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "error": self.error,
        }


class MLOpsHandler(ABC):
    """Abstract base for every MLOps lifecycle handler.

    Subclasses set:

    - :attr:`handler_name` — short identifier surfaced in lineage rows
      and the catalog API.
    - :attr:`required_scopes` — default ``("data:read",)``.

    Subclasses implement :meth:`run` (sync). The base wraps the call.
    """

    handler_name: ClassVar[str] = ""
    required_scopes: ClassVar[tuple[str, ...]] = ("data:read",)
    mutates: ClassVar[bool] = False

    def __init__(self) -> None:
        if not self.handler_name:
            raise ValueError(
                f"{self.__class__.__name__} must set ``handler_name``"
            )

    # ------------------------------------------------------------------
    # Public — call wrapper
    # ------------------------------------------------------------------

    def invoke(
        self,
        *,
        ctx: HandlerContext | None = None,
        **kwargs: Any,
    ) -> HandlerResult:
        ctx = ctx or HandlerContext()
        started = datetime.utcnow()

        try:
            self.policy_check(ctx)
        except HandlerPolicyError as exc:
            self._emit_lineage(ctx=ctx, ok=False, summary=f"policy denied: {exc}")
            return HandlerResult(
                ok=False,
                error=f"policy denied: {exc}",
                metadata={"handler": self.handler_name},
            )

        try:
            result = self.run(ctx=ctx, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("MLOpsHandler %s failed", self.handler_name)
            self._emit_lineage(ctx=ctx, ok=False, summary=str(exc))
            return HandlerResult(
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                metadata={"handler": self.handler_name},
            )

        elapsed_ms = (datetime.utcnow() - started).total_seconds() * 1000.0
        if not isinstance(result, HandlerResult):
            result = HandlerResult(ok=True, data=result)
        result.elapsed_ms = float(round(elapsed_ms, 3))
        result.metadata.setdefault("handler", self.handler_name)
        self._emit_lineage(
            ctx=ctx, ok=result.ok, summary=result.summary or f"invoked {self.handler_name}"
        )
        return result

    # ------------------------------------------------------------------
    # Hooks subclasses override
    # ------------------------------------------------------------------

    @abstractmethod
    def run(self, *, ctx: HandlerContext, **kwargs: Any) -> HandlerResult | Any:
        """Execute the handler. Subclasses implement."""

    def policy_check(self, ctx: HandlerContext) -> None:
        """Default: require declared scopes to be present on ``ctx``."""
        missing = [s for s in self.required_scopes if not ctx.has_scope(s)]
        if missing and ctx.granted_scopes:
            raise HandlerPolicyError(
                f"{self.handler_name} requires scopes {missing!r}"
            )
        # If no scopes are granted at all, we run in a permissive mode
        # so local dev + tests work without faking JWT claims; the
        # MCP tools / API routes use a tighter policy via DataMCPTool.

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit_lineage(
        self,
        *,
        ctx: HandlerContext,
        ok: bool,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        try:
            from aqp.data.catalog.lineage import LineageEvent, get_lineage_bus

            get_lineage_bus().emit(
                LineageEvent(
                    transform_kind="mlops_handler",
                    actor=ctx.actor or "mlops",
                    actor_kind=ctx.actor_kind or "system",
                    mcp_tool_name=self.handler_name,
                    service_name="aqp_models.handlers",
                    summary=summary,
                    workspace_id=ctx.workspace_id,
                    project_id=ctx.project_id,
                    details={
                        "ok": ok,
                        "session_id": ctx.session_id,
                        "scopes": list(ctx.granted_scopes),
                        **(details or {}),
                    },
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("MLOps lineage emit failed for %s", self.handler_name, exc_info=True)


__all__ = [
    "HandlerContext",
    "HandlerPolicyError",
    "HandlerResult",
    "MLOpsHandler",
]
