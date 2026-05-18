"""Iceberg namespace policy aspect.

Operators write an icebergNamespacePolicy aspect on a MetadataEntity
to declare a non-default Iceberg namespace prefix for that entity
(workspace, project, lab, or organisation). When register_dataset()
resolves a namespace, it consults the aspect store FIRST; missing
aspect falls back to the canonical aqp_bronze_/silver_/gold_ defaults.
"""
from __future__ import annotations

import logging
import re
from typing import ClassVar

from pydantic import Field, ValidationInfo, field_validator

from aqp.metadata.openmetadata.base import AQPOpenMetadataBase, _urn_validator

logger = logging.getLogger(__name__)

_PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9_]*_$")
_REGULATORY_RESERVED_PREFIXES: tuple[str, ...] = (
    "aqp_cfpb",
    "aqp_uspto",
    "aqp_fda",
    "aqp_sec",
)


class IcebergNamespacePolicy(AQPOpenMetadataBase):
    """Aspect payload describing a scope-specific Iceberg namespace policy."""

    aspect_name: ClassVar[str] = "icebergNamespacePolicy"

    scope_urn: str = Field(
        ...,
        description=(
            "AQP URN of the entity this policy applies to "
            "(workspace / project / lab / org)."
        ),
    )
    bronze_prefix: str = Field(
        default="aqp_bronze_",
        min_length=4,
        max_length=64,
        description=(
            "Namespace prefix for bronze-tier datasets owned by this scope. "
            "Defaults to aqp_bronze_."
        ),
    )
    silver_prefix: str = Field(
        default="aqp_silver_",
        min_length=4,
        max_length=64,
        description="Namespace prefix for silver-tier datasets.",
    )
    gold_prefix: str = Field(
        default="aqp_gold_",
        min_length=4,
        max_length=64,
        description="Namespace prefix for gold-tier datasets.",
    )
    allowed_extra_prefixes: list[str] = Field(
        default_factory=list,
        description=(
            "Additional non-medallion prefixes this scope may write to, "
            "eg. aqp_lab_, aqp_project_<id>_."
        ),
    )
    forbidden_prefixes: list[str] = Field(
        default_factory=list,
        description=(
            "Prefixes this scope explicitly cannot write to. Always includes "
            "aqp_cfpb, aqp_uspto, aqp_fda, and aqp_sec."
        ),
    )

    _validate_scope_urn = _urn_validator("scope_urn")

    @field_validator("bronze_prefix", "silver_prefix", "gold_prefix", mode="after")
    @classmethod
    def _validate_prefix(cls, value: str, info: ValidationInfo) -> str:
        """Validate namespace prefixes and normalize them to lowercase."""
        prefix = str(value or "").strip().lower()
        field_name = info.field_name or "prefix"
        if not prefix.endswith("_"):
            raise ValueError(f"{field_name} must end with '_'")
        if not _PREFIX_PATTERN.fullmatch(prefix):
            raise ValueError(
                f"{field_name} must match ^[a-z][a-z0-9_]*_$, got {value!r}"
            )
        return prefix

    @field_validator("allowed_extra_prefixes", mode="after")
    @classmethod
    def _normalize_allowed_prefixes(cls, value: list[str]) -> list[str]:
        """Trim and deduplicate allowed extra namespace prefixes."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for prefix in value:
            candidate = str(prefix or "").strip().lower()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            cleaned.append(candidate)
        return cleaned

    @field_validator("forbidden_prefixes", mode="after")
    @classmethod
    def _ensure_reserved_forbidden(cls, value: list[str]) -> list[str]:
        """Always include reserved regulatory namespaces in forbidden prefixes."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for prefix in (*_REGULATORY_RESERVED_PREFIXES, *(value or [])):
            candidate = str(prefix or "").strip().lower()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            cleaned.append(candidate)
        return cleaned


__all__ = ["IcebergNamespacePolicy"]
