"""Iceberg namespace policy aspects."""
from __future__ import annotations

import logging
from typing import ClassVar, Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from aqp.metadata.openmetadata.base import AQPOpenMetadataBase, _urn_validator

logger = logging.getLogger(__name__)


class NamespacePrefixOverride(AQPOpenMetadataBase):
    """Layer-scoped namespace prefix override."""

    layer: Literal["bronze", "silver", "gold"] = Field(
        ...,
        description="Medallion layer this prefix override applies to.",
    )
    prefix: str = Field(
        ...,
        description=(
            "Replacement namespace prefix, eg. 'tenant_w42_bronze_'. "
            "Must end with an underscore."
        ),
    )
    description: str | None = Field(
        default=None,
        description="Operator-readable rationale for this override.",
    )

    @field_validator("prefix", mode="after")
    @classmethod
    def _validate_prefix(cls, value: str, info: ValidationInfo) -> str:
        """Require non-empty prefixes with a trailing underscore."""
        prefix = str(value or "").strip()
        if not prefix:
            raise ValueError("prefix cannot be empty")
        if not prefix.endswith("_"):
            field_name = info.field_name or "prefix"
            raise ValueError(
                f"{field_name} must end with '_' to stay namespace-safe, got {value!r}"
            )
        return prefix


class IcebergNamespacePolicy(AQPOpenMetadataBase):
    """Aspect payload defining scoped Iceberg namespace prefix policy."""

    entity_type: ClassVar[str] = "policy"
    aspect_name: ClassVar[str] = "icebergNamespacePolicy"

    urn: str = Field(
        ...,
        description=(
            "AQP URN of the policy entity, eg. "
            "urn:aqp:policy:prod:workspace_w42_iceberg_namespaces."
        ),
    )
    scope: Literal["global", "workspace", "project", "domain", "env"] = Field(
        ...,
        description=(
            "Scope at which this policy applies. The resolver picks the "
            "most-specific matching policy at lookup time."
        ),
    )
    scope_value: str | None = Field(
        default=None,
        description=(
            "Identifier of the scope (workspace_id, project_id, domain name). "
            "Required when scope != 'global'."
        ),
    )
    overrides: list[NamespacePrefixOverride] = Field(
        default_factory=list,
        description="Per-layer prefix overrides for this scope.",
    )
    allow_extra_namespaces: list[str] = Field(
        default_factory=list,
        description=(
            "Additional namespaces this scope is permitted to write to even "
            "without a layer prefix match. Use sparingly; bronze/silver/gold "
            "should cover the 99% case."
        ),
    )
    priority: int = Field(
        default=100,
        ge=1,
        le=1000,
        description=(
            "Higher priority policies win when multiple match. Built-in "
            "default is 100; per-scope overrides typically use 200."
        ),
    )
    active: bool = Field(
        default=True,
        description="When False, the resolver skips this policy.",
    )

    _validate_urn = _urn_validator("urn")

    @model_validator(mode="after")
    def _validate_scope_value(self) -> IcebergNamespacePolicy:
        """Require ``scope_value`` for non-global policy scopes."""
        if self.scope != "global" and not str(self.scope_value or "").strip():
            raise ValueError("scope_value is required when scope is not 'global'")
        return self


__all__ = ["IcebergNamespacePolicy", "NamespacePrefixOverride"]
