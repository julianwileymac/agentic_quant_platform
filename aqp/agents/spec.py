"""Declarative AgentSpec — the reproducible blueprint for any agent.

An :class:`AgentSpec` is the configuration contract every spec-driven
agent honours. It is loaded from YAML or constructed in code and
persisted (immutably, hash-locked) in ``agent_spec_versions`` so a
historical run can always be replayed against the exact spec it was
built from.

Spec composition
----------------

```yaml
name: research.equity
role: equity_researcher
description: "Long-form equity research synthesis"
system_prompt: "You are a senior equity research analyst. ..."
model:
  provider: ollama
  model: nemotron:latest
  tier: deep
  temperature: 0.2
tools: [rag_query, hierarchy_browse, fundamentals_snapshot, news_digest]
memory:
  kind: redis_hybrid
  role: research.equity
  working_max: 64
rag:
  - levels: [l1, l2]
    orders: [second]
    corpora: [sec_filings, sec_xbrl, financial_ratios, earnings_call]
    per_level_k: 5
  - levels: [l3]
    orders: [third]
    corpora: [cfpb_complaints, fda_recalls, uspto_patents]
    per_level_k: 3
guardrails:
  output_schema: "aqp.agents.spec.JsonSchema"
  cost_budget_usd: 1.0
  rate_limit_per_minute: 30
  pii_redact: false
output_schema: aqp.agents.research.equity_researcher.EquityReport
max_cost_usd: 1.5
max_calls: 25
annotations: ["alpha_base", "research"]
```
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class ModelRef(BaseModel):
    """LLM provider + model + tier."""

    provider: str = "ollama"
    model: str = ""
    tier: Literal["deep", "quick"] = "deep"
    temperature: float = 0.2
    max_tokens: int | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class ToolRef(BaseModel):
    """Reference to a tool in :data:`aqp.agents.tools.TOOL_REGISTRY`."""

    name: str
    kwargs: dict[str, Any] = Field(default_factory=dict)


class MemorySpec(BaseModel):
    """Per-role memory binding."""

    kind: Literal["none", "bm25", "hybrid", "redis_hybrid"] = "redis_hybrid"
    role: str = "default"
    persist_dir: str | None = None
    retrieval_top_k: int = 5
    working_max: int = 64
    write_through: bool = True

    def disabled(self) -> bool:
        return self.kind == "none"


class RAGRef(BaseModel):
    """A single RAG retrieval clause inside an agent spec."""

    levels: list[Literal["l0", "l1", "l2", "l3"]] = Field(default_factory=lambda: ["l3"])
    orders: list[Literal["first", "second", "third"]] = Field(default_factory=lambda: ["first", "second", "third"])
    corpora: list[str] = Field(default_factory=list)
    per_level_k: int = 5
    final_k: int = 8
    rerank: bool = True
    compress: bool = True
    inject_as: str = "context"  # "context" | "system" | "memory"

    @field_validator("levels")
    @classmethod
    def _at_least_one_level(cls, v: list[str]) -> list[str]:
        if not v:
            return ["l3"]
        return v


class GuardrailSpec(BaseModel):
    """Output validation + cost / rate / content guards."""

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


class AgentSpec(BaseModel):
    """Declarative blueprint for one agent.

    Snapshotting
    ------------
    :meth:`snapshot_hash` returns the SHA256 of the canonical JSON form
    (sorted keys, no whitespace). Persisting a spec via
    :func:`aqp.agents.registry.persist_spec` writes one new
    :class:`AgentSpecVersion` whenever the hash changes; that row is
    referenced by every :class:`AgentRunV2` so a run can be replayed
    against the exact spec that produced it.
    """

    name: str
    role: str
    description: str = ""
    system_prompt: str = ""
    model: ModelRef = Field(default_factory=ModelRef)
    tools: list[ToolRef] = Field(default_factory=list)
    memory: MemorySpec = Field(default_factory=MemorySpec)
    rag: list[RAGRef] = Field(default_factory=list)
    guardrails: GuardrailSpec = Field(default_factory=GuardrailSpec)
    output_schema: str | None = None
    max_cost_usd: float = 1.0
    max_calls: int = 20
    annotations: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tools", mode="before")
    @classmethod
    def _coerce_tools(cls, v: Any) -> list[Any]:
        if not v:
            return []
        out: list[Any] = []
        for item in v:
            if isinstance(item, str):
                out.append({"name": item})
            else:
                out.append(item)
        return out

    @field_validator("rag", mode="before")
    @classmethod
    def _coerce_rag(cls, v: Any) -> list[Any]:
        if v is None:
            return []
        if isinstance(v, dict):
            return [v]
        return list(v)

    def snapshot_hash(self) -> str:
        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def memory_role(self) -> str:
        return self.memory.role or self.name

    @classmethod
    def from_yaml_path(cls, path: str) -> "AgentSpec":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    @classmethod
    def from_yaml_str(cls, content: str) -> "AgentSpec":
        data = yaml.safe_load(content) or {}
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


def load_specs_from_dir(dir_path: str, *, suffix: str = ".yaml") -> Iterable[AgentSpec]:
    """Yield every spec yaml under ``dir_path``."""
    from pathlib import Path

    root = Path(dir_path)
    if not root.exists():
        return
    for p in sorted(root.glob(f"*{suffix}")):
        try:
            yield AgentSpec.from_yaml_path(str(p))
        except Exception:  # noqa: BLE001
            continue


__all__ = [
    "AgentSpec",
    "GuardrailSpec",
    "MemorySpec",
    "ModelRef",
    "RAGRef",
    "ToolRef",
    "load_specs_from_dir",
]
