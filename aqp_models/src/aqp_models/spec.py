"""MLSkillSpec -- hash-locked snapshot of an MLOps skill recipe.

Mirrors :class:`aqp.agents.spec.AgentSpec` /
:class:`aqp.bots.spec.BotSpec` /
:class:`aqp_rl.spec.RLExperimentSpec` /
:class:`aqp.analysis.spec.AnalysisSpec`: a Pydantic body + a SHA-256
hash + persistence via a ``ml_skill_versions`` row. Changing the spec
body means a new version row, never an in-place mutation
(``aqp.mdc`` cardinal rule, AGENTS rule 13/15/17/24).

A skill composites multiple MLOps interfaces. The seed pack ships:

- ``regime_aware_alpha`` — Classifier (regime detector) + Predictor
  (regime-specialised alpha) chained behind an OOD rule pack.
- ``multi_horizon_forecast`` — Forecaster (variable-horizon) +
  Analyzer (sentiment overlay).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


SkillKind = Literal[
    "regime_aware_alpha",
    "multi_horizon_forecast",
    "anomaly_screen",
    "sentiment_overlay",
    "custom",
]


class SkillStep(BaseModel):
    """One interface invocation inside a skill."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Display label for the step")
    interface_kind: Literal[
        "predictor",
        "forecaster",
        "classifier",
        "segmenter",
        "analyzer",
    ]
    model_ref: str = Field(
        ...,
        description=(
            "Resolvable model identifier — either an alias registered in "
            "``aqp.core.registry`` or a fully-qualified module path."
        ),
    )
    kwargs: dict[str, Any] = Field(default_factory=dict)
    output_alias: str | None = Field(
        default=None,
        description=(
            "Optional name the next step can reference (e.g. 'regime' -> "
            "subsequent predictor uses the classified regime to pick a head)."
        ),
    )


class SkillGuardrails(BaseModel):
    """Inference-time safety + cost guards."""

    model_config = ConfigDict(extra="forbid")

    rule_pack: str = "ood_default"
    cost_budget_usd: float = 1.0
    max_runtime_ms: int = 30_000
    require_workspace: bool = True


class MLSkillSpec(BaseModel):
    """Hash-locked MLOps skill spec."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    kind: SkillKind = "custom"
    steps: list[SkillStep] = Field(default_factory=list)
    guardrails: SkillGuardrails = Field(default_factory=SkillGuardrails)
    annotations: list[str] = Field(default_factory=list)
    workspace_id: str | None = None
    project_id: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("steps")
    @classmethod
    def _non_empty(cls, v: list[SkillStep]) -> list[SkillStep]:
        if not v:
            raise ValueError("MLSkillSpec.steps must contain at least one entry")
        return v

    def canonical_body(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json", exclude={"workspace_id", "project_id"}
        )

    def spec_hash(self) -> str:
        canonical = json.dumps(self.canonical_body(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_yaml_path(cls, path: str) -> "MLSkillSpec":
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls.model_validate(data)

    @classmethod
    def from_yaml_str(cls, body: str) -> "MLSkillSpec":
        data = yaml.safe_load(body) or {}
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


def load_skill_specs_from_dir(dir_path: str, *, suffix: str = ".yaml") -> Iterable[MLSkillSpec]:
    from pathlib import Path

    root = Path(dir_path)
    if not root.exists():
        return
    for p in sorted(root.glob(f"*{suffix}")):
        try:
            yield MLSkillSpec.from_yaml_path(str(p))
        except Exception:  # noqa: BLE001
            continue


__all__ = [
    "MLSkillSpec",
    "SkillGuardrails",
    "SkillKind",
    "SkillStep",
    "load_skill_specs_from_dir",
]
