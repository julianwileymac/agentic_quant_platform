"""OpenMetadata-style glossary and document metadata models."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import ClassVar

from pydantic import Field, ValidationInfo, field_validator

from aqp.metadata.openmetadata.base import AQPOpenMetadataBase, _urn_validator

logger = logging.getLogger(__name__)


class GlossaryTerm(AQPOpenMetadataBase):
    """Defines a financial/domain term that can be attached to documents."""

    name: str = Field(..., description="Canonical glossary term name.")
    definition: str = Field(
        ...,
        description="Clear operator-readable definition of the term.",
    )
    synonyms: list[str] = Field(
        default_factory=list,
        description="Alternative names used for this term.",
    )
    related_terms: list[str] = Field(
        default_factory=list,
        description="Other glossary term names that are conceptually related.",
    )
    urn: str | None = Field(
        default=None,
        description="Optional AQP URN for this glossary entry.",
    )

    @field_validator("urn", mode="after")
    @classmethod
    def _validate_optional_urn(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        """Validate glossary URNs when present."""
        if value is None:
            return None
        return cls.validate_urn(value, info)


class Document(AQPOpenMetadataBase):
    """Metadata record for an ingested research or reference document."""

    entity_type: ClassVar[str] = "document"
    aspect_name: ClassVar[str] = "documentMetadata"

    urn: str = Field(..., description="AQP URN of the document.")
    instrument_urn: str | None = Field(
        default=None,
        description="AQP URN of the primary instrument referenced.",
    )
    valid_from: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp when this document became valid.",
    )
    valid_to: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp when this document ceased being valid.",
    )
    glossary_terms: list[str] = Field(
        default_factory=list,
        description="Formal financial terms discussed in this document.",
    )
    content_text: str | None = Field(
        default=None,
        description=(
            "The document body text. May be omitted when only metadata is being recorded."
        ),
    )
    source_url: str | None = Field(
        default=None,
        description="Optional source URL where the document originated.",
    )
    language: str | None = Field(
        default=None,
        description="ISO-639 language code, eg. 'en'.",
    )

    _validate_urn = _urn_validator("urn")

    @field_validator("instrument_urn", mode="after")
    @classmethod
    def _validate_instrument_urn(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        """Validate optional instrument URNs when present."""
        if value is None:
            return None
        return cls.validate_urn(value, info)


__all__ = ["Document", "GlossaryTerm"]
