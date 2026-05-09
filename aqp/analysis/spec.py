"""Declarative ``AnalysisSpec`` — reproducible analysis blueprint.

Mirrors :class:`aqp.rl.spec.RLExperimentSpec`,
:class:`aqp.bots.spec.BotSpec`, and :class:`aqp.agents.spec.AgentSpec`.
A spec is hash-locked: identical specs collapse to one
``analysis_spec_versions`` row, and any historical run can always be
replayed against the exact spec it was built from.

Spec composition
----------------

```yaml
name: spy-distribution-audit
slug: spy-distribution-audit
kind: research
description: Distribution + GARCH + outlier audit for SPY daily bars.

dataset:
  iceberg_identifier: aqp_silver_alpha_vantage.equities_daily
  filters:
    vt_symbol: "SPY.NYSE"
  limit: 5000

steps:
  - alias: profile
    flow_ref:
      flow: profiling.describe
      params: {}

  - alias: returns_dist
    flow_ref:
      flow: distribution.descriptive_stats
      params:
        column: log_return

  - alias: shapiro
    flow_ref:
      flow: distribution.shapiro_wilk
      params:
        column: log_return

  - alias: garch
    flow_ref:
      flow: time_series.garch
      params:
        column: log_return
        p: 1
        q: 1
        horizon: 10

medallion_layer: gold
business_metadata:
  data_owner: research-team
  semantic_definition: SPY daily distribution + volatility audit.
  domain: research.distribution_audit
  sla_class: tier-3-eod
```
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AnalysisSpecKind = Literal["research", "diagnostic", "production", "ad_hoc"]
"""Discriminator for the kind of run the spec describes."""


class DatasetRef(BaseModel):
    """Where the spec sources its primary input.

    Three resolution modes (in priority order):

    1. ``iceberg_identifier`` — ``"namespace.name"`` read via
       :func:`aqp.data.iceberg_catalog.read_arrow`.
    2. ``dataset_version_id`` — a registered
       :class:`aqp.persistence.models.DatasetVersion` row.
    3. ``dataset_cfg`` — inline ``{class, module_path, kwargs}`` for
       ad-hoc handler-driven datasets (mirrors ``/ml/flows`` payloads).

    ``filters`` / ``limit`` apply uniformly across the three modes.
    """

    iceberg_identifier: str | None = None
    dataset_version_id: str | None = None
    dataset_cfg: dict[str, Any] | None = None

    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    limit: int | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _at_least_one_source(self) -> "DatasetRef":
        if not (self.iceberg_identifier or self.dataset_version_id or self.dataset_cfg):
            raise ValueError(
                "DatasetRef requires one of iceberg_identifier, dataset_version_id, or dataset_cfg"
            )
        return self

    def descriptor(self) -> str:
        """Stable string descriptor for logging + Iceberg row stamping."""
        if self.iceberg_identifier:
            return f"iceberg:{self.iceberg_identifier}"
        if self.dataset_version_id:
            return f"dataset_version:{self.dataset_version_id}"
        cfg = self.dataset_cfg or {}
        cls = cfg.get("class") or cfg.get("module_path") or "<inline>"
        return f"cfg:{cls}"


class FlowRef(BaseModel):
    """Reference to a registered analysis flow (by namespaced name)."""

    flow: str = Field(..., description="e.g. 'distribution.shapiro_wilk'")
    params: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, str] = Field(
        default_factory=dict,
        description="Map of named upstream inputs. Values reference step "
        "aliases. '$dataset' is reserved for the spec dataset.",
    )

    @field_validator("flow")
    @classmethod
    def _strip_flow(cls, value: str) -> str:
        out = (value or "").strip()
        if not out:
            raise ValueError("FlowRef.flow must be a non-empty namespaced name")
        return out


class AnalysisStep(BaseModel):
    """One step in the spec — a flow ref with a stable alias."""

    alias: str
    flow_ref: FlowRef
    persist: bool = True
    notes: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    @field_validator("alias")
    @classmethod
    def _alias_shape(cls, value: str) -> str:
        out = (value or "").strip()
        if not out:
            raise ValueError("AnalysisStep.alias must be non-empty")
        if not re.match(r"^[A-Za-z0-9_\-:.]+$", out):
            raise ValueError(
                f"AnalysisStep.alias {out!r} must be alphanumeric / -_:."
            )
        return out


class BusinessMetadataRef(BaseModel):
    """Subset of :class:`aqp.data.catalog.active_metadata.BusinessMetadata`.

    We don't import the dataclass here to keep ``aqp.analysis.spec``
    lightweight (the runtime translates this into the real dataclass
    only when an Iceberg write happens).
    """

    data_owner: str
    semantic_definition: str
    reliability_score: float | None = None
    sla_class: str | None = None
    domain: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class AnalysisSpec(BaseModel):
    """Hash-locked declarative blueprint for one analysis run."""

    name: str
    slug: str = ""
    kind: AnalysisSpecKind = "research"
    description: str = ""

    dataset: DatasetRef
    steps: list[AnalysisStep]

    medallion_layer: Literal["gold"] = "gold"
    business_metadata: BusinessMetadataRef | None = None

    annotations: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    # ---------------------------------------------------- validation

    @model_validator(mode="after")
    def _ensure_slug(self) -> "AnalysisSpec":
        if not self.slug:
            self.slug = _slugify(self.name) if self.name else ""
        else:
            self.slug = _slugify(self.slug)
        return self

    @model_validator(mode="after")
    def _unique_aliases(self) -> "AnalysisSpec":
        seen: set[str] = set()
        for step in self.steps:
            if step.alias in seen:
                raise ValueError(f"duplicate AnalysisStep.alias {step.alias!r}")
            seen.add(step.alias)
        return self

    @field_validator("annotations", mode="before")
    @classmethod
    def _coerce_annotations(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return list(value)

    # ---------------------------------------------------- snapshotting

    def snapshot_hash(self) -> str:
        """SHA256 over the canonical JSON form (sorted keys, no whitespace)."""
        payload = self.model_dump(mode="json")
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ---------------------------------------------------- YAML helpers

    @classmethod
    def from_yaml_path(cls, path: str) -> "AnalysisSpec":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    @classmethod
    def from_yaml_str(cls, content: str) -> "AnalysisSpec":
        data = yaml.safe_load(content) or {}
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80]


def load_specs_from_dir(
    dir_path: str, *, suffix: str = ".yaml"
) -> Iterable[AnalysisSpec]:
    """Yield every analysis spec yaml under ``dir_path`` (recursively)."""
    from pathlib import Path

    root = Path(dir_path)
    if not root.exists():
        return
    for p in sorted(root.rglob(f"*{suffix}")):
        try:
            yield AnalysisSpec.from_yaml_path(str(p))
        except Exception:  # noqa: BLE001
            continue


__all__ = [
    "AnalysisSpec",
    "AnalysisSpecKind",
    "AnalysisStep",
    "BusinessMetadataRef",
    "DatasetRef",
    "FlowRef",
    "load_specs_from_dir",
]
