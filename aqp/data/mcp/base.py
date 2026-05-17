"""DataMCPTool ABC + supporting types.

This is the single base class every data-layer MCP tool subclasses.
Tools are registered with :func:`aqp.data.mcp.registry.register_data_mcp_tool`
so both transports (in-process bridge + external MCP server) read
from the same registry.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Iterable

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MCPPolicyError(PermissionError):
    """Raised when a DataMCPTool ``policy_check`` rejects the call."""


@dataclass(slots=True)
class MCPToolContext:
    """Per-call context the tool sees on every invocation.

    Carries the actor (user, agent, session), tenancy ids, and
    granted scopes. Tools use this to enforce
    :func:`aqp.data.mcp.policy.enforce_tenancy` and
    :func:`enforce_read_only_for_session`.
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
class MCPToolResult:
    """Structured outcome of an MCP tool invocation."""

    ok: bool
    data: Any = None
    summary: str | None = None
    rows_returned: int | None = None
    elapsed_ms: float | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "data": self.data,
            "summary": self.summary,
            "rows_returned": self.rows_returned,
            "elapsed_ms": self.elapsed_ms,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "error": self.error,
        }


class DataMCPTool(ABC):
    """Abstract base for every data-layer MCP tool.

    Subclasses set:

    - :attr:`name` — alias used in the registry, OpenAI tool names,
      and MCP server tool names. ``snake_case``.
    - :attr:`description` — short semantic description for the LLM
      router (what does this tool do? when should the LLM call it?).
    - :attr:`args_schema` — Pydantic model describing input parameters.
      Used to render the OpenAI / MCP JSON schema.
    - :attr:`mutates` — ``True`` if the tool writes / triggers
      side-effects. Used by :func:`policy.enforce_read_only_for_session`.
    - :attr:`required_scopes` — tuple of scope strings required to
      invoke the tool. Read-only tools default to ``("data:read",)``.
    - :attr:`tags` — free-form tags surfaced in the catalog API.

    Subclasses implement :meth:`run` (sync). The base class wraps
    the call with policy checks, lineage emission, and error
    capture so every tool produces a uniform :class:`MCPToolResult`.
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    args_schema: ClassVar[type[BaseModel] | None] = None
    mutates: ClassVar[bool] = False
    required_scopes: ClassVar[tuple[str, ...]] = ("data:read",)
    tags: ClassVar[tuple[str, ...]] = ()
    category: ClassVar[str] = "general"
    """Coarse grouping for the UI catalog (catalog/entities/pipelines/sinks/...)."""

    # ------------------------------------------------------------------
    # Public surface (concrete)
    # ------------------------------------------------------------------

    def invoke(
        self,
        *,
        ctx: MCPToolContext | None = None,
        **arguments: Any,
    ) -> MCPToolResult:
        """Validate arguments, enforce policy, execute, and emit lineage.

        Returns a uniform :class:`MCPToolResult`. Validation /
        policy errors are surfaced through ``ok=False`` with a human-
        readable ``error`` string rather than re-raised, so the LLM
        can recover gracefully.
        """
        ctx = ctx or MCPToolContext()
        started = datetime.utcnow()
        validated: dict[str, Any] = {}
        if self.args_schema is not None:
            try:
                model = self.args_schema(**arguments)
                validated = model.model_dump() if hasattr(model, "model_dump") else dict(arguments)
            except Exception as exc:  # noqa: BLE001
                return MCPToolResult(
                    ok=False,
                    error=f"args validation failed: {exc}",
                    metadata={"tool": self.name},
                )
        else:
            validated = dict(arguments)

        try:
            self.policy_check(ctx)
        except MCPPolicyError as exc:
            self._emit_lineage(ctx=ctx, ok=False, summary=f"policy denied: {exc}")
            return MCPToolResult(
                ok=False,
                error=f"policy denied: {exc}",
                metadata={"tool": self.name},
            )

        try:
            result = self.run(ctx=ctx, **validated)
        except Exception as exc:  # noqa: BLE001
            logger.exception("DataMCPTool %s failed", self.name)
            self._emit_lineage(ctx=ctx, ok=False, summary=str(exc))
            return MCPToolResult(
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                metadata={"tool": self.name},
            )

        elapsed_ms = (datetime.utcnow() - started).total_seconds() * 1000.0
        if not isinstance(result, MCPToolResult):
            result = MCPToolResult(ok=True, data=result)
        result.elapsed_ms = float(round(elapsed_ms, 3))
        result.metadata.setdefault("tool", self.name)
        self._emit_lineage(
            ctx=ctx, ok=result.ok, summary=result.summary or f"invoked {self.name}"
        )
        return result

    # ------------------------------------------------------------------
    # Hooks subclasses override
    # ------------------------------------------------------------------

    @abstractmethod
    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult | Any:
        """Execute the tool. Subclasses implement; never call directly.

        Subclasses MUST treat ``arguments`` as already-validated by
        :attr:`args_schema`. Return either a :class:`MCPToolResult`
        (preferred, lets the tool report rows / warnings explicitly)
        or any JSON-serialisable object.
        """

    def policy_check(self, ctx: MCPToolContext) -> None:
        """Default policy: require all ``required_scopes`` on the context.

        Subclasses can override to add tenancy / rate / data-minimization
        constraints. Concrete enforcement lives in
        :mod:`aqp.data.mcp.policy`.
        """
        from aqp.data.mcp.policy import enforce_required_scopes

        enforce_required_scopes(ctx, self.required_scopes)

    # ------------------------------------------------------------------
    # Schema / metadata accessors
    # ------------------------------------------------------------------

    @classmethod
    def to_openai_function(cls) -> dict[str, Any]:
        """OpenAI-style function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": cls._json_schema(),
            },
        }

    @classmethod
    def to_mcp_tool_descriptor(cls) -> dict[str, Any]:
        """MCP-style tool descriptor (subset of OpenAI shape)."""
        return {
            "name": cls.name,
            "description": cls.description,
            "inputSchema": cls._json_schema(),
            "mutates": bool(cls.mutates),
            "category": cls.category,
            "tags": list(cls.tags),
            "required_scopes": list(cls.required_scopes),
        }

    @classmethod
    def _json_schema(cls) -> dict[str, Any]:
        if cls.args_schema is None:
            return {"type": "object", "properties": {}}
        try:
            return cls.args_schema.model_json_schema()
        except Exception:  # noqa: BLE001 - pydantic v1 fallback
            try:
                return cls.args_schema.schema()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                return {"type": "object", "properties": {}}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _emit_lineage(
        self, *, ctx: MCPToolContext, ok: bool, summary: str
    ) -> None:
        try:
            from aqp.data.catalog.lineage import LineageEvent, get_lineage_bus

            get_lineage_bus().emit(
                LineageEvent(
                    transform_kind="mcp_tool",
                    actor=ctx.actor or "mcp",
                    actor_kind=ctx.actor_kind or "agent",
                    mcp_tool_name=self.name,
                    service_name="data_mcp",
                    summary=summary,
                    workspace_id=ctx.workspace_id,
                    project_id=ctx.project_id,
                    details={
                        "ok": ok,
                        "session_id": ctx.session_id,
                        "scopes": list(ctx.granted_scopes),
                    },
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("MCP lineage emit failed for %s", self.name, exc_info=True)


def coerce_iterable(value: Any) -> Iterable[Any]:
    """Helper: coerce ``None`` / scalars / iterables to a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


__all__ = [
    "DataMCPTool",
    "MCPPolicyError",
    "MCPToolContext",
    "MCPToolResult",
    "coerce_iterable",
]
