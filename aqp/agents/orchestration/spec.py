"""``WorkflowSpec`` — declarative blueprint for a single workflow run.

Phase 2 ships the minimum schema the :class:`WorkflowRuntime` needs:
``name`` / ``adapter`` (alias) / ``params`` / ``max_rounds`` /
``guardrails`` / ``description`` / ``annotations``. Phase 5 enriches
this with:

- :meth:`snapshot_hash` already lives here (it's needed for replay
  semantics from day one).
- ``from_yaml`` / ``to_yaml`` helpers (already shipped here).
- The persistence side — ``workflow_spec_versions`` ORM rows + the
  ``persist_spec`` / ``replay_spec_version`` registry helpers in
  :mod:`aqp.agents.orchestration.registry_specs` — lands in Phase 5
  behind ``orchestration_workflow_versioning_enabled``.

Snapshotting
------------
:meth:`snapshot_hash` returns the SHA256 of the canonical JSON form
(sorted keys, no whitespace), mirroring
:class:`aqp.agents.spec.AgentSpec` so the registry can hash-lock
workflow versions with the exact same idempotency semantics.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from aqp.agents.orchestration.registry import ADAPTER_KINDS


class WorkflowGuardrails(BaseModel):
    """Cost / call / time caps that the :class:`WorkflowRuntime` enforces."""

    cost_budget_usd: float = 5.0
    max_calls: int = 100
    max_duration_seconds: int = 1800
    forbidden_terms: list[str] = Field(default_factory=list)
    require_rationale: bool = False

    @field_validator("forbidden_terms")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [t.lower() for t in v]


class WorkflowScheduleRef(BaseModel):
    """Optional cron / interval schedule consumed by the Phase 3
    :class:`AutomationScheduleAdapter`. Empty fields mean
    "no schedule" — the workflow only runs on-demand.
    """

    cron: str = ""
    interval_seconds: int = 0
    timezone: str = "UTC"
    enabled: bool = False


class WorkflowSpec(BaseModel):
    """Declarative blueprint for one workflow run.

    A workflow selects exactly one :class:`OrchestrationAdapter`
    (``adapter`` field references the alias registered by the
    metaclass). The adapter dispatches internally — composite flows
    that mix Crew + Graph + Debate are themselves the responsibility
    of a dedicated adapter (Phase 5 ``WorkflowStudioAdapter``).

    Phase 2 shape::

        name: research.dialectical_v1
        description: "Bull/Bear debate + portfolio judge"
        adapter: DialecticalDebateAdapter
        params:
          builder: dialectical
          agent_spec_bull: research.bull_researcher
          agent_spec_bear: research.bear_researcher
        max_rounds: 2
        schedule:
          cron: "0 13 * * 1-5"
          enabled: false
        guardrails:
          cost_budget_usd: 2.0
          max_calls: 30
        annotations: ["research", "dialectical"]
    """

    name: str
    description: str = ""
    adapter: str
    """Alias of the :class:`OrchestrationAdapter` to invoke. Resolved
    through :func:`aqp.agents.orchestration.registry.get_adapter`."""
    adapter_kind: str | None = None
    """Optional sub-kind hint for the studio dropdown / validation."""
    params: dict[str, Any] = Field(default_factory=dict)
    """Free-form adapter-specific parameters. Each adapter documents
    its required keys."""
    max_rounds: int = 1
    """Cap forwarded to debate-style adapters and the bounded
    :func:`aqp.agents.graph.dialectical.build_dialectical_debate_graph`."""
    schedule: WorkflowScheduleRef = Field(default_factory=WorkflowScheduleRef)
    guardrails: WorkflowGuardrails = Field(default_factory=WorkflowGuardrails)
    annotations: list[str] = Field(default_factory=list)
    template_target: Literal[
        "research", "selection", "trader", "analysis", "live", "paper", "utility"
    ] = "utility"
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("adapter_kind")
    @classmethod
    def _validate_adapter_kind(cls, v: str | None) -> str | None:
        if v is not None and v not in ADAPTER_KINDS:
            raise ValueError(
                f"adapter_kind must be one of {ADAPTER_KINDS}; got {v!r}"
            )
        return v

    @field_validator("max_rounds")
    @classmethod
    def _validate_max_rounds(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"max_rounds must be >= 1, got {v!r}")
        return int(v)

    def snapshot_hash(self) -> str:
        """SHA256 of the canonical JSON dump (sorted keys, no whitespace).

        Mirrors :meth:`aqp.agents.spec.AgentSpec.snapshot_hash` so the
        Phase 5 ``workflow_spec_versions`` registry can dedupe versions
        with the same idempotency contract.
        """
        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ IO
    @classmethod
    def from_yaml_path(cls, path: str) -> "WorkflowSpec":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    @classmethod
    def from_yaml_str(cls, content: str) -> "WorkflowSpec":
        data = yaml.safe_load(content) or {}
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


def load_workflow_specs_from_dir(
    dir_path: str, *, suffix: str = ".yaml"
) -> Iterable[WorkflowSpec]:
    """Yield every spec yaml under ``dir_path``.

    Mirrors :func:`aqp.agents.spec.load_specs_from_dir` so the Phase 5
    studio can scan ``configs/workflows/`` the same way the agent
    registry scans ``configs/agents/``.
    """
    from pathlib import Path

    root = Path(dir_path)
    if not root.exists():
        return
    for p in sorted(root.glob(f"*{suffix}")):
        try:
            yield WorkflowSpec.from_yaml_path(str(p))
        except Exception:  # noqa: BLE001
            continue


__all__ = [
    "WorkflowGuardrails",
    "WorkflowScheduleRef",
    "WorkflowSpec",
    "load_workflow_specs_from_dir",
]
