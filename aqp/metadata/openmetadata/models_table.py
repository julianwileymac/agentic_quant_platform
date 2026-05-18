"""OpenMetadata-style table and namespace policy metadata models."""
from __future__ import annotations

import logging
import re
from typing import Any, ClassVar, Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from aqp.metadata.openmetadata.base import AQPOpenMetadataBase, _urn_validator
from aqp.metadata.urn import parse_urn

logger = logging.getLogger(__name__)
_NAMESPACE_PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}_$")


class TableColumn(AQPOpenMetadataBase):
    """Describes a single dataset column."""

    name: str = Field(..., description="Column name as stored in the dataset schema.")
    data_type: str = Field(
        ...,
        description="PyArrow or SQL data type string for this column.",
    )
    nullable: bool = Field(
        ...,
        description="Whether this column accepts null values.",
    )
    description: str | None = Field(
        default=None,
        description="Optional business definition for the column.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags associated with this column.",
    )


class TableConstraint(AQPOpenMetadataBase):
    """Constraint metadata attached to one or more columns."""

    constraint_type: Literal["PRIMARY_KEY", "UNIQUE", "NOT_NULL", "FOREIGN_KEY", "CHECK"] = Field(
        ...,
        description="Constraint category applied to the referenced columns.",
    )
    columns: list[str] = Field(
        ...,
        description="Ordered list of column names covered by this constraint.",
    )
    description: str | None = Field(
        default=None,
        description="Optional operator-readable explanation for this constraint.",
    )


class DatasetTable(AQPOpenMetadataBase):
    """OpenMetadata-style representation of a dataset/table entity."""

    entity_type: ClassVar[str] = "dataset"
    aspect_name: ClassVar[str] = "datasetProperties"

    urn: str = Field(
        ...,
        description="AQP URN of the dataset table.",
    )
    name: str = Field(
        ...,
        description="Human-friendly dataset table name.",
    )
    iceberg_identifier: str = Field(
        ...,
        description="Canonical Iceberg identifier in namespace.table form.",
    )
    medallion_layer: Literal["bronze", "silver", "gold"] | None = Field(
        default=None,
        description="Optional medallion layer assigned to this dataset.",
    )
    columns: list[TableColumn] = Field(
        default_factory=list,
        description="Column definitions for the dataset schema.",
    )
    constraints: list[TableConstraint] = Field(
        default_factory=list,
        description="Optional table-level and column-level constraints.",
    )
    description: str | None = Field(
        default=None,
        description="Optional operator-readable description of the table.",
    )
    business_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary business metadata captured for the table.",
    )

    _validate_urn = _urn_validator("urn")


class IcebergNamespacePolicy(AQPOpenMetadataBase):
    """Aspect payload describing medallion namespace prefix overrides."""

    entity_type: ClassVar[str] = "namespace_policy"
    aspect_name: ClassVar[str] = "icebergNamespacePolicy"

    urn: str = Field(
        ...,
        description=(
            "AQP URN of the namespace_policy entity, eg. "
            "urn:aqp:namespace_policy:prod:default or "
            "urn:aqp:namespace_policy:prod:tenant_acme."
        ),
    )
    policy_name: str = Field(
        ...,
        description="Operator-friendly name for the policy.",
    )
    bronze_prefix: str = Field(
        default="aqp_bronze_",
        description=(
            "Iceberg namespace prefix for the bronze (raw) medallion layer. "
            "MUST end with an underscore."
        ),
    )
    silver_prefix: str = Field(
        default="aqp_silver_",
        description="Iceberg namespace prefix for the silver (normalised) medallion layer.",
    )
    gold_prefix: str = Field(
        default="aqp_gold_",
        description="Iceberg namespace prefix for the gold (entity-centric) medallion layer.",
    )
    applies_to_workspace_id: str | None = Field(
        default=None,
        description=(
            "When set, this policy ONLY applies inside the named workspace. "
            "When None, the policy is global / project-default."
        ),
    )
    applies_to_project_id: str | None = Field(
        default=None,
        description="When set, this policy ONLY applies inside the named project.",
    )
    applies_to_domain_pattern: str | None = Field(
        default=None,
        description=(
            "Optional regex pattern matched against BusinessMetadata.domain. "
            "Allows per-domain prefix routing."
        ),
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=1000,
        description=(
            "Higher priority wins when multiple policies match. "
            "The hardcoded LAYER_PREFIXES defaults are treated as priority=0."
        ),
    )
    # Backward-compatible fields retained for legacy namespace policy tools.
    scope_urn: str | None = Field(
        default=None,
        description="Legacy scope URN retained for backwards compatibility.",
    )
    allowed_extra_prefixes: list[str] = Field(
        default_factory=list,
        description="Legacy allow-list of extra namespace prefixes.",
    )
    forbidden_prefixes: list[str] = Field(
        default_factory=list,
        description="Legacy deny-list of namespace prefixes.",
    )

    @model_validator(mode="before")
    @classmethod
    def _apply_legacy_backfill(
        cls,
        raw: Any,
    ) -> Any:
        if not isinstance(raw, dict):
            return raw
        payload = dict(raw)
        scope_urn = str(payload.get("scope_urn") or "").strip() or None
        if not payload.get("urn") and scope_urn:
            payload["urn"] = scope_urn
        if not str(payload.get("policy_name") or "").strip():
            inferred_name = str(payload.get("urn") or "namespace_policy_default").strip()
            payload["policy_name"] = inferred_name
        if scope_urn:
            try:
                parsed_scope = parse_urn(scope_urn)
            except ValueError:
                parsed_scope = None
            if parsed_scope is not None:
                if (
                    parsed_scope.entity_type == "workspace"
                    and not payload.get("applies_to_workspace_id")
                ):
                    payload["applies_to_workspace_id"] = parsed_scope.id
                if (
                    parsed_scope.entity_type == "project"
                    and not payload.get("applies_to_project_id")
                ):
                    payload["applies_to_project_id"] = parsed_scope.id
        return payload

    @field_validator("urn", mode="after")
    @classmethod
    def _validate_urn(cls, value: str, _info: ValidationInfo) -> str:
        parse_urn(value)
        return value

    @field_validator("scope_urn", mode="after")
    @classmethod
    def _validate_scope_urn(cls, value: str | None, _info: ValidationInfo) -> str | None:
        if value is None:
            return None
        parse_urn(value)
        return value

    @field_validator("bronze_prefix", "silver_prefix", "gold_prefix", mode="after")
    @classmethod
    def _validate_prefix(cls, value: str, info: ValidationInfo) -> str:
        prefix = str(value or "").strip()
        if not prefix.endswith("_"):
            raise ValueError(f"{info.field_name} must end with '_'")
        if not _NAMESPACE_PREFIX_PATTERN.fullmatch(prefix):
            raise ValueError(
                f"{info.field_name} must match '^[a-z][a-z0-9_]{{0,63}}_$'"
            )
        return prefix

    @field_validator("allowed_extra_prefixes", "forbidden_prefixes", mode="after")
    @classmethod
    def _normalise_legacy_prefix_lists(
        cls,
        value: list[str],
        _info: ValidationInfo,
    ) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for prefix in value:
            candidate = str(prefix or "").strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            out.append(candidate)
        return out


__all__ = [
    "DatasetTable",
    "IcebergNamespacePolicy",
    "TableColumn",
    "TableConstraint",
]
