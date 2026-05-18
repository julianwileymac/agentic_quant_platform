"""Declarative :class:`AssistantSpec` blueprint for the Assistant Engine.

An ``AssistantSpec`` is the contract every interactive assistant
honours. It is loaded from YAML or constructed in code and persisted
(immutably, hash-locked) in ``assistant_spec_versions`` so a
historical assistant run can always be replayed against the exact spec
that produced it (mirrors :class:`aqp.agents.spec.AgentSpec` and
:class:`aqp.agents.orchestration.spec.WorkflowSpec`).

An assistant is a thin dispatcher: it never owns its own LLM call
loop. ``mode="agent"`` routes through
:class:`aqp.agents.runtime.AgentRuntime`; ``mode="workflow"`` routes
through :class:`aqp.agents.orchestration.runtime.WorkflowRuntime`. New
behaviour requires a new ``AssistantSpec`` version — historical rows
in ``assistant_spec_versions`` are immutable.

YAML shape::

    name: platform_assistant
    description: "Interactive AQP platform assistant."
    mode: agent
    agent_spec_name: codebase_assistant
    system_instructions: |
      You are the AQP platform assistant.
    starter_prompts:
      - "Where does AQP define AgentRuntime?"
    tool_policy:
      read_only: true
      allowed_tools: [codebase.search]
      explicit_scopes: []
    memory_policy:
      enabled: true
      include_recent_messages: 12
    sandbox_policy:
      enabled: false
      backend: blocked
    annotations: ["assistant", "codebase"]
    template_target: utility
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class AssistantModelPolicy(BaseModel):
    """Optional per-assistant model overlay.

    ``provider`` / ``model`` / ``tier`` / ``temperature`` override the
    target spec's :class:`aqp.agents.spec.ModelRef` for the duration of
    the assistant run. Leaving any field as the default keeps the
    target spec's value. The runtime forwards every override through
    :func:`aqp.llm.providers.router.router_complete` (rule 2 — no
    direct LLM SDK calls from assistant code).
    """

    provider: str | None = None
    model: str | None = None
    tier: Literal["deep", "quick"] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class AssistantToolPolicy(BaseModel):
    """Tool-grant policy enforced by the assistant runtime.

    ``read_only`` is the default safety posture. When ``True`` the
    runtime never grants ``data:write`` even if the underlying agent
    spec declares write tools.

    ``allowed_tools`` is an opt-in whitelist. An empty list means "use
    every tool the underlying agent / workflow already exposes" —
    matching the existing AgentRuntime behaviour. A non-empty list
    narrows the catalog to those tool names; tools outside the list
    are filtered out before the LLM tool dispatch loop sees them.

    ``explicit_scopes`` is appended to the spec-time scope grant the
    DataMCP bridge plumbs onto :class:`aqp.data.mcp.base.MCPToolContext`.
    Mutating tools require an entry here (e.g. ``["data:write"]``).
    """

    read_only: bool = True
    allowed_tools: list[str] = Field(default_factory=list)
    explicit_scopes: list[str] = Field(default_factory=list)

    @field_validator("explicit_scopes")
    @classmethod
    def _scopes_distinct(cls, v: list[str]) -> list[str]:
        return sorted({s for s in v if s})


class AssistantMemoryPolicy(BaseModel):
    """Per-assistant short-term memory overlay.

    Memory itself lives in :class:`aqp.llm.memory.RedisHybridMemory`
    (rule 11 / 12); the assistant runtime simply controls how much
    recent history is replayed into the system prompt before the
    underlying ``AgentRuntime`` / ``WorkflowRuntime`` runs.
    """

    enabled: bool = True
    include_recent_messages: int = Field(default=12, ge=0, le=200)
    role: str | None = None


class AssistantSandboxPolicy(BaseModel):
    """Sandbox policy enforced by :class:`aqp.assistants.sandbox.AssistantSandbox`.

    Default is ``backend="blocked"`` — the sandbox validates commands
    against the deny list but never executes anything. Flipping
    ``backend`` to ``"docker"`` / ``"microvm"`` is the explicit
    operator opt-in; the assistant runtime never grants execution
    purely from a prompt.
    """

    enabled: bool = False
    backend: Literal["blocked", "docker", "microvm"] = "blocked"
    workspace_root: str | None = None


class AssistantSpec(BaseModel):
    """Declarative blueprint for one interactive assistant.

    Snapshotting
    ------------
    :meth:`snapshot_hash` returns the SHA256 of the canonical JSON
    form (sorted keys, no whitespace). Persisting via
    :func:`aqp.assistants.registry.persist_spec` writes one new
    ``AssistantSpecVersion`` whenever the hash changes; that row is
    referenced by every ``AssistantRun`` so a run can be replayed
    against the exact spec that produced it. Mirrors
    :meth:`aqp.agents.spec.AgentSpec.snapshot_hash` and
    :meth:`aqp.agents.orchestration.spec.WorkflowSpec.snapshot_hash`.
    """

    name: str
    description: str = ""
    mode: Literal["agent", "workflow"] = "agent"
    agent_spec_name: str | None = None
    workflow_spec_name: str | None = None
    system_instructions: str = ""
    starter_prompts: list[str] = Field(default_factory=list)
    model_policy: AssistantModelPolicy = Field(default_factory=AssistantModelPolicy)
    tool_policy: AssistantToolPolicy = Field(default_factory=AssistantToolPolicy)
    memory_policy: AssistantMemoryPolicy = Field(default_factory=AssistantMemoryPolicy)
    sandbox_policy: AssistantSandboxPolicy = Field(default_factory=AssistantSandboxPolicy)
    annotations: list[str] = Field(default_factory=list)
    template_target: Literal[
        "research", "selection", "trader", "analysis", "live", "paper", "utility"
    ] = "utility"
    extras: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_target(self) -> "AssistantSpec":
        if self.mode == "agent" and not self.agent_spec_name:
            raise ValueError(
                "AssistantSpec(mode='agent') requires agent_spec_name"
            )
        if self.mode == "workflow" and not self.workflow_spec_name:
            raise ValueError(
                "AssistantSpec(mode='workflow') requires workflow_spec_name"
            )
        return self

    @property
    def target_kind(self) -> str:
        return "agent" if self.mode == "agent" else "workflow"

    @property
    def target_ref(self) -> str:
        return self.agent_spec_name if self.mode == "agent" else (
            self.workflow_spec_name or ""
        )

    def snapshot_hash(self) -> str:
        """SHA256 of the canonical JSON dump (sorted keys, no whitespace)."""
        payload = self.model_dump(mode="json")
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_yaml_path(cls, path: str) -> "AssistantSpec":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(_normalise_payload(data))

    @classmethod
    def from_yaml_str(cls, content: str) -> "AssistantSpec":
        data = yaml.safe_load(content) or {}
        return cls.model_validate(_normalise_payload(data))

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


def _normalise_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Map the YAML keys used by the in-tree configs onto the typed model.

    The configs at ``configs/assistants/*.yaml`` use ``tool_policy`` /
    ``memory_policy`` / ``sandbox_policy`` block names already; this
    helper coerces a few legacy aliases (``model``) into the typed
    submodels without forcing operators to rewrite YAML.
    """
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    if "model" in out and "model_policy" not in out:
        out["model_policy"] = out.pop("model")
    return out


def load_specs_from_dir(
    dir_path: str, *, suffix: str = ".yaml"
) -> Iterable[AssistantSpec]:
    """Yield every ``AssistantSpec`` YAML under ``dir_path``."""
    from pathlib import Path

    root = Path(dir_path)
    if not root.exists():
        return
    for p in sorted(root.glob(f"*{suffix}")):
        try:
            yield AssistantSpec.from_yaml_path(str(p))
        except Exception:  # noqa: BLE001 - keep registry boot tolerant
            continue


__all__ = [
    "AssistantMemoryPolicy",
    "AssistantModelPolicy",
    "AssistantSandboxPolicy",
    "AssistantSpec",
    "AssistantToolPolicy",
    "load_specs_from_dir",
]
