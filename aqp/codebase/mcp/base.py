"""CodebaseMCPTool ABC + supporting types.

Single base class every codebase-layer MCP tool subclasses, mirroring
:class:`aqp.data.mcp.base.DataMCPTool`. Subclasses implement
:meth:`run`; the base class wraps the call with policy checks, timing,
and uniform :class:`MCPToolResult` shape.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MCPPolicyError(PermissionError):
    """Raised when a :class:`CodebaseMCPTool` policy check rejects the call."""


@dataclass(slots=True)
class MCPToolContext:
    """Per-call context the tool sees on every invocation.

    Mirrors :class:`aqp.data.mcp.base.MCPToolContext` but uses
    ``code:*`` default scopes. ``workspace_root`` is the absolute
    filesystem path the codebase tools are allowed to touch — the
    policy layer rejects any path that escapes it.
    """

    actor: str | None = None
    actor_kind: str | None = None  # user | agent | service | system
    session_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    workspace_root: str | None = None
    granted_scopes: tuple[str, ...] = ()
    request_id: str | None = None
    received_at: datetime = field(default_factory=datetime.utcnow)
    extras: dict[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return scope in self.granted_scopes


@dataclass(slots=True)
class MCPToolResult:
    """Structured outcome of a codebase MCP tool invocation."""

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


class CodebaseMCPTool(ABC):
    """Abstract base for every codebase-layer MCP tool.

    Subclasses set:

    - :attr:`name` — alias used in the registry. ``snake_case`` with
      a ``codebase.`` prefix.
    - :attr:`description` — short semantic description for the LLM
      router.
    - :attr:`args_schema` — Pydantic model describing input
      parameters; used for the OpenAI / MCP JSON schema.
    - :attr:`mutates` — ``True`` if the tool writes / triggers
      side-effects (i.e. anything that touches the filesystem or an
      external service). Read-only tools default to ``False``.
    - :attr:`required_scopes` — tuple of scope strings required to
      invoke the tool. Defaults to ``("code:read",)``.
    - :attr:`tags` / :attr:`category` — free-form metadata surfaced
      in the catalog API.

    Subclasses implement :meth:`run` (sync). The base class wraps
    the call with policy checks and error capture so every tool
    produces a uniform :class:`MCPToolResult`.
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    args_schema: ClassVar[type[BaseModel] | None] = None
    mutates: ClassVar[bool] = False
    required_scopes: ClassVar[tuple[str, ...]] = ("code:read",)
    tags: ClassVar[tuple[str, ...]] = ()
    category: ClassVar[str] = "general"

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def invoke(
        self,
        *,
        ctx: MCPToolContext | None = None,
        **arguments: Any,
    ) -> MCPToolResult:
        """Validate arguments, enforce policy, execute, capture errors."""
        ctx = ctx or MCPToolContext()
        started = datetime.utcnow()
        validated: dict[str, Any] = {}
        if self.args_schema is not None:
            try:
                model = self.args_schema(**arguments)
                validated = (
                    model.model_dump() if hasattr(model, "model_dump") else dict(arguments)
                )
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
            return MCPToolResult(
                ok=False,
                error=f"policy denied: {exc}",
                metadata={"tool": self.name},
            )

        try:
            result = self.run(ctx=ctx, **validated)
        except Exception as exc:  # noqa: BLE001
            logger.exception("CodebaseMCPTool %s failed", self.name)
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
        return result

    # ------------------------------------------------------------------
    # Hooks subclasses override
    # ------------------------------------------------------------------

    @abstractmethod
    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult | Any:
        """Execute the tool. Subclasses implement; never called directly."""

    def policy_check(self, ctx: MCPToolContext) -> None:
        """Default policy: require all ``required_scopes`` on the context."""
        from aqp.codebase.mcp.policy import enforce_required_scopes

        enforce_required_scopes(ctx, self.required_scopes)

    # ------------------------------------------------------------------
    # Schema / metadata
    # ------------------------------------------------------------------

    @classmethod
    def to_openai_function(cls) -> dict[str, Any]:
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
        except Exception:  # noqa: BLE001
            try:
                return cls.args_schema.schema()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                return {"type": "object", "properties": {}}


__all__ = [
    "CodebaseMCPTool",
    "MCPPolicyError",
    "MCPToolContext",
    "MCPToolResult",
]
