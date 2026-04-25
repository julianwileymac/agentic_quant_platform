"""First-class agent capability config — tools, MCP, memory, guardrails, structured output.

Every :class:`IAlphaModel` that drives an LLM/agent (today
:class:`AgenticAlpha`) accepts an :class:`AgentCapabilities` block via
its constructor. The wizard hydrates this from registry-driven
dropdowns; backtests / live runs all consume the same shape.

The shape is **declarative** — :class:`CapabilityRuntime` in
:mod:`aqp.agents.capability_runtime` resolves it into runtime objects
(bound CrewAI ``BaseTool`` instances, MCP clients, memory backends,
guardrail validators).

Defaults preserve the current single-LLM-call behaviour so existing
configs keep working.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class McpServerSpec(BaseModel):
    """One Model Context Protocol server the agent can call.

    Either ``command`` (stdio) or ``url`` (HTTP / SSE) must be set.
    ``tools`` is an optional allowlist — when empty, every tool exposed
    by the server is callable.
    """

    name: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    transport: Literal["stdio", "sse", "http"] = "stdio"
    tools: list[str] = Field(default_factory=list)
    timeout_s: float = 30.0


class MemorySpec(BaseModel):
    """Per-role memory binding — see :mod:`aqp.llm.memory`."""

    kind: Literal["none", "bm25", "hybrid"] = "bm25"
    role: str = "default"
    persist_dir: str | None = None
    retrieval_top_k: int = 3
    write_through: bool = True

    def disabled(self) -> bool:
        return self.kind == "none"


class GuardrailSpec(BaseModel):
    """Output validation + cost / rate / content guards.

    ``output_schema`` accepts either a JSON-schema dict *or* a fully
    qualified Pydantic model name (``"aqp.agents.trading.types.AgentDecision"``)
    — both are honoured by :class:`CapabilityRuntime.validate_output`.
    """

    output_schema: dict[str, Any] | str | None = None
    cost_budget_usd: float = 1.0
    rate_limit_per_minute: int = 60
    pii_redact: bool = False
    forbidden_terms: list[str] = Field(default_factory=list)
    require_rationale: bool = True
    min_confidence: float | None = None

    @field_validator("forbidden_terms")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [t.lower() for t in v]


class AgentCapabilities(BaseModel):
    """Aggregate capabilities config for a single agent / alpha."""

    tools: list[str] = Field(
        default_factory=list,
        description="Names from ``aqp.agents.tools.get_tool`` registry.",
    )
    mcp_servers: list[McpServerSpec] = Field(default_factory=list)
    memory: MemorySpec | None = None
    guardrails: GuardrailSpec | None = None
    output_schema: dict[str, Any] | str | None = Field(
        default=None,
        description="Shortcut for ``guardrails.output_schema``; ignored when guardrails is set.",
    )
    max_cost_usd: float = 1.0
    max_calls: int = 20

    def effective_guardrails(self) -> GuardrailSpec:
        if self.guardrails is not None:
            return self.guardrails
        return GuardrailSpec(
            output_schema=self.output_schema,
            cost_budget_usd=self.max_cost_usd,
        )


__all__ = [
    "AgentCapabilities",
    "GuardrailSpec",
    "McpServerSpec",
    "MemorySpec",
]
