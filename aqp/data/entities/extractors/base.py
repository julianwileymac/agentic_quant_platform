"""Entity extractor base class.

Each extractor reads rows from one Iceberg table (or pandas frame),
yields :class:`EntityCandidate` dicts, and the framework upserts them
through :class:`aqp.data.entities.EntityRegistry`.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from aqp.data.entities.registry import EntityRegistry


@dataclass
class EntityCandidate:
    """One extracted entity.

    Mirrors the kwargs of :func:`upsert_entity` and adds optional
    ``identifiers``, ``relations``, ``annotations`` lists for the
    framework to upsert in the same transaction window.
    """

    kind: str
    canonical_name: str
    primary_identifier: str | None = None
    primary_identifier_scheme: str | None = None
    short_name: str | None = None
    description: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    confidence: float | None = None
    instrument_id: str | None = None
    issuer_id: str | None = None
    parent_id: str | None = None
    identifiers: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    annotations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Aggregate counts returned by :meth:`EntityExtractor.run`."""

    candidates: int = 0
    entities_upserted: int = 0
    identifiers_upserted: int = 0
    relations_upserted: int = 0
    annotations_upserted: int = 0
    attached: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "entities_upserted": self.entities_upserted,
            "identifiers_upserted": self.identifiers_upserted,
            "relations_upserted": self.relations_upserted,
            "annotations_upserted": self.annotations_upserted,
            "attached": self.attached,
            "errors": list(self.errors),
        }


class EntityExtractor:
    """Base extractor class.

    Subclasses override :meth:`extract`. The framework calls
    :meth:`run`, which iterates over the source rows and upserts via
    :class:`EntityRegistry`.
    """

    name: str = "extractor"
    source_dataset: str | None = None
    extractor_id: str = ""

    def __init__(
        self,
        *,
        source_dataset: str | None = None,
        registry: EntityRegistry | None = None,
        attach_dataset_catalog_id: str | None = None,
        attach_dataset_version_id: str | None = None,
        attach_iceberg_identifier: str | None = None,
    ) -> None:
        self.source_dataset = source_dataset or self.source_dataset
        self.registry = registry or EntityRegistry()
        self.attach_dataset_catalog_id = attach_dataset_catalog_id
        self.attach_dataset_version_id = attach_dataset_version_id
        self.attach_iceberg_identifier = attach_iceberg_identifier
        self.extractor_id = self.extractor_id or self.__class__.__name__

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    def extract(self, rows: Iterable[Any]) -> Iterator[EntityCandidate]:
        """Yield :class:`EntityCandidate` from raw input rows."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, rows: Iterable[Any]) -> ExtractionResult:
        result = ExtractionResult()
        for candidate in self.extract(rows):
            result.candidates += 1
            try:
                upserted = self.registry.upsert(
                    kind=candidate.kind,
                    canonical_name=candidate.canonical_name,
                    primary_identifier=candidate.primary_identifier,
                    primary_identifier_scheme=candidate.primary_identifier_scheme,
                    short_name=candidate.short_name,
                    description=candidate.description,
                    attributes=candidate.attributes,
                    tags=candidate.tags,
                    confidence=candidate.confidence,
                    source_dataset=self.source_dataset,
                    source_extractor=self.extractor_id,
                    instrument_id=candidate.instrument_id,
                    issuer_id=candidate.issuer_id,
                    parent_id=candidate.parent_id,
                )
                if upserted is None:
                    continue
                result.entities_upserted += 1
                entity_id = upserted["id"]
                for ident in candidate.identifiers:
                    if self.registry.link_identifier(entity_id=entity_id, **ident):
                        result.identifiers_upserted += 1
                for rel in candidate.relations:
                    if self.registry.add_relation(subject_id=entity_id, **rel):
                        result.relations_upserted += 1
                for note in candidate.annotations:
                    if self.registry.annotate(entity_id=entity_id, **note):
                        result.annotations_upserted += 1
                if (
                    self.attach_dataset_catalog_id
                    or self.attach_dataset_version_id
                    or self.attach_iceberg_identifier
                ):
                    self.registry.attach(
                        entity_id=entity_id,
                        dataset_catalog_id=self.attach_dataset_catalog_id,
                        dataset_version_id=self.attach_dataset_version_id,
                        iceberg_identifier=self.attach_iceberg_identifier,
                        role="extracted_from",
                    )
                    result.attached += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{self.extractor_id}: {exc}")
        return result


__all__ = ["EntityCandidate", "EntityExtractor", "ExtractionResult"]
