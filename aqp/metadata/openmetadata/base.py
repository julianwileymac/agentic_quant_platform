"""Base Pydantic V2 models for OpenMetadata-compatible payloads."""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from aqp.metadata.urn import parse_urn

logger = logging.getLogger(__name__)


class AQPOpenMetadataBase(BaseModel):
    """Strict base class for all OpenMetadata-style entities and aspects."""

    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        extra="forbid",
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )

    entity_type: ClassVar[str | None] = None
    """Entity discriminator used by schema exporters."""

    aspect_name: ClassVar[str | None] = None
    """Aspect discriminator used by schema/PDL exporters."""

    @classmethod
    def validate_urn(cls, value: str, info: ValidationInfo) -> str:
        """Validate a single AQP URN value and return the canonical input."""
        field_name = info.field_name or "<unknown>"
        try:
            parse_urn(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid AQP URN in field '{field_name}': {value!r}. {exc}"
            ) from exc
        return value


def _urn_validator(field_name: str) -> Any:
    """Return a reusable `field_validator` that enforces AQP URN format."""

    @field_validator(field_name, mode="after")
    @classmethod
    def _validate_urn_field(
        cls: type[AQPOpenMetadataBase], value: str, info: ValidationInfo
    ) -> str:
        return cls.validate_urn(value, info)

    return _validate_urn_field


__all__ = ["AQPOpenMetadataBase", "_urn_validator"]
