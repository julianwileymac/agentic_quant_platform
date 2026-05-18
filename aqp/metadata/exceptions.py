"""Exceptions for the consolidated metadata aspect store."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ImmutableAspectError(Exception):
    """Raised when an immutable aspect row is mutated in place."""

    def __init__(self, aspect_id: str, urn: str, aspect_name: str) -> None:
        self.aspect_id = str(aspect_id)
        self.urn = str(urn)
        self.aspect_name = str(aspect_name)
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            "EntityAspect rows are immutable; create a new version instead "
            f"(id={self.aspect_id!r}, urn={self.urn!r}, aspect_name={self.aspect_name!r})."
        )


class MetadataValidationError(Exception):
    """Raised when metadata payload validation fails."""

    def __init__(
        self,
        fields: list[str],
        guidance: str,
        original: BaseException | None = None,
    ) -> None:
        self.fields = list(fields)
        self.guidance = str(guidance)
        self.original = original
        base = (
            f"Metadata validation failed for fields={self.fields}. "
            f"Guidance: {self.guidance}"
        )
        if original is not None:
            base = f"{base} (original={original!r})"
        super().__init__(base)

