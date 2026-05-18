"""Hash-locked :class:`TerraformStackSpec` and supporting ref types.

Mirrors :class:`aqp.bots.spec.BotSpec` / :class:`aqp.agents.spec.AgentSpec`
shape: the spec is a Pydantic model, the canonical-JSON SHA-256 hash
is computed by :meth:`snapshot_hash`, and re-snapshotting through
:func:`aqp.terraform.registry.persist_spec` produces a new
``terraform_stack_spec_versions`` row only when the hash changes.

A spec describes *what* to render (module kind + modules + variables
+ outputs + resources + backend); the matching codegen emitter in
:mod:`aqp.terraform.codegen` turns it into HCL. Operators can also
bypass codegen entirely by referencing a pre-authored module via
``modules[].source``.

API parity notes:

- ``slug`` auto-derives from ``name`` (lowercase + hyphens) when
  not supplied.
- ``variables`` is a list of typed :class:`TerraformVariableRef`
  rows (so codegen can emit proper ``variable {}`` blocks).
- ``modules`` / ``resources`` / ``outputs`` are typed ref lists so
  the templates render a full HCL document, not just a single
  module block.
- :meth:`to_yaml` / :meth:`from_yaml_str` provide a round-trippable
  serialisation for `configs/terraform/*.yaml` operator stacks.
- :meth:`spec_hash` is preserved as an alias for
  :meth:`snapshot_hash` so existing callers don't break.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aqp.persistence.models_terraform import (
    TERRAFORM_ENVIRONMENTS,
    TERRAFORM_MODULE_KINDS,
    TERRAFORM_PROVIDER_KINDS,
    TERRAFORM_STATE_BACKENDS,
)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    """Lowercase + hyphen-collapse a free-text string for use as a slug."""
    text = (value or "").strip().lower()
    text = _SLUG_RE.sub("-", text).strip("-")
    return text or "stack"


# ---------------------------------------------------------------------------
# Ref objects
# ---------------------------------------------------------------------------


class TerraformVariableRef(BaseModel):
    """One HCL ``variable {}`` block."""

    model_config = ConfigDict(extra="forbid")
    name: str
    type: str = "string"
    default: Any = None
    description: str | None = None
    sensitive: bool = False


class TerraformOutputRef(BaseModel):
    """One HCL ``output {}`` block."""

    model_config = ConfigDict(extra="forbid")
    name: str
    value: Any
    description: str | None = None
    sensitive: bool = False


class TerraformModuleRef(BaseModel):
    """One HCL ``module {}`` block referencing a Terraform module."""

    model_config = ConfigDict(extra="forbid")
    name: str
    source: str
    version: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    # Per-module provider aliasing (e.g. {"aws.east": "aws.east"}).
    providers: dict[str, str] = Field(default_factory=dict)


class TerraformResourceRef(BaseModel):
    """One HCL ``resource {}`` block (any provider + type)."""

    model_config = ConfigDict(extra="forbid")
    type: str
    name: str
    body: dict[str, Any] = Field(default_factory=dict)


class TerraformBackendRef(BaseModel):
    """How the rendered stack persists Terraform state."""

    model_config = ConfigDict(extra="forbid")
    kind: str = "local"
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        if value not in TERRAFORM_STATE_BACKENDS:
            raise ValueError(
                f"unknown state backend {value!r}; valid: {TERRAFORM_STATE_BACKENDS}"
            )
        return value


class TerraformProviderRef(BaseModel):
    """Reference to a registered :class:`TerraformProvider` row."""

    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    kind: str = "local"
    region: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        if value and value not in TERRAFORM_PROVIDER_KINDS:
            raise ValueError(
                f"unknown provider kind {value!r}; valid: {TERRAFORM_PROVIDER_KINDS}"
            )
        return value


# Alias for backwards compat — older code paths may still import this name.
TerraformBackendSpec = TerraformBackendRef


# ---------------------------------------------------------------------------
# Top-level spec
# ---------------------------------------------------------------------------


class TerraformStackSpec(BaseModel):
    """Hash-locked spec for a Terraform stack."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=240)
    slug: str = Field(default="", max_length=120)
    module_kind: str = "composite"
    description: str | None = None

    cloud_provider: str = "local"
    environment: str = "local"

    provider: TerraformProviderRef = Field(default_factory=TerraformProviderRef)
    backend: TerraformBackendRef = Field(default_factory=TerraformBackendRef)

    variables: list[TerraformVariableRef] = Field(default_factory=list)
    modules: list[TerraformModuleRef] = Field(default_factory=list)
    resources: list[TerraformResourceRef] = Field(default_factory=list)
    outputs: list[TerraformOutputRef] = Field(default_factory=list)

    module_source: str | None = None
    common_tags: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)

    # Required-provider pins emitted into the ``terraform {}`` block.
    # Each entry is ``{"source": "...", "version": "..."}``. Empty
    # dict picks safe defaults (null + random).
    required_providers: dict[str, dict[str, str]] = Field(default_factory=dict)

    # Optional tenancy stamps that downstream tagging picks up.
    organization_id: str | None = None
    workspace_id: str | None = None

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("module_kind")
    @classmethod
    def _validate_module_kind(cls, value: str) -> str:
        if value not in TERRAFORM_MODULE_KINDS:
            raise ValueError(
                f"unknown module kind {value!r}; valid: {TERRAFORM_MODULE_KINDS}"
            )
        return value

    @field_validator("cloud_provider")
    @classmethod
    def _validate_cloud(cls, value: str) -> str:
        if value not in TERRAFORM_PROVIDER_KINDS:
            raise ValueError(
                f"unknown cloud_provider {value!r}; valid: {TERRAFORM_PROVIDER_KINDS}"
            )
        return value

    @field_validator("environment")
    @classmethod
    def _validate_env(cls, value: str) -> str:
        if value not in TERRAFORM_ENVIRONMENTS:
            raise ValueError(
                f"unknown environment {value!r}; valid: {TERRAFORM_ENVIRONMENTS}"
            )
        return value

    @model_validator(mode="after")
    def _ensure_slug(self) -> TerraformStackSpec:
        if not self.slug:
            object.__setattr__(self, "slug", _slugify(self.name))
        return self

    # ------------------------------------------------------------------
    # Hash + serialisation
    # ------------------------------------------------------------------

    def canonical_json(self) -> str:
        """Return a deterministic JSON serialisation for hashing."""
        payload = self.model_dump(mode="json", exclude_none=False)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def snapshot_hash(self) -> str:
        """SHA-256 of the canonical JSON (matches AGENTS rule 43)."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    # Backwards-compat alias used by earlier code paths.
    def spec_hash(self) -> str:
        return self.snapshot_hash()

    def to_yaml(self) -> str:
        """Round-trippable YAML dump.

        Use :meth:`from_yaml_str` to reverse. Hash equality across the
        round-trip is asserted by ``tests/terraform/test_spec.py``.
        """
        return yaml.safe_dump(
            self.model_dump(mode="json", exclude_none=False),
            sort_keys=True,
            allow_unicode=True,
        )

    @classmethod
    def from_yaml_str(cls, payload: str) -> TerraformStackSpec:
        data = yaml.safe_load(payload) or {}
        if not isinstance(data, dict):
            raise ValueError("YAML payload must decode to a mapping")
        return cls.model_validate(data)


__all__ = [
    "TerraformBackendRef",
    "TerraformBackendSpec",
    "TerraformModuleRef",
    "TerraformOutputRef",
    "TerraformProviderRef",
    "TerraformResourceRef",
    "TerraformStackSpec",
    "TerraformVariableRef",
]
