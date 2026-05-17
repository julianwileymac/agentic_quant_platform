"""High-level facade over the unified entity registry tables."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from aqp.data.entities.graph_store import get_graph_store
from aqp.persistence.db import get_session
from aqp.persistence.models_entity_registry import (
    EntityAnnotation,
    EntityDatasetLink,
    EntityIdentifier,
    EntityRelation,
    EntityRow,
)

logger = logging.getLogger(__name__)


def _graph_store() -> Any:
    try:
        return get_graph_store()
    except Exception as exc:  # noqa: BLE001
        logger.debug("entity graph store unavailable: %s", exc)
        return None


def _coerce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        from dateutil import parser  # type: ignore

        return parser.parse(str(value))
    except Exception:  # noqa: BLE001
        return None


def upsert_entity(
    *,
    kind: str,
    canonical_name: str,
    primary_identifier: str | None = None,
    primary_identifier_scheme: str | None = None,
    short_name: str | None = None,
    description: str | None = None,
    attributes: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    confidence: float | None = None,
    source_dataset: str | None = None,
    source_extractor: str | None = None,
    instrument_id: str | None = None,
    issuer_id: str | None = None,
    parent_id: str | None = None,
    is_canonical: bool | None = None,
) -> dict[str, Any] | None:
    """Create or update an entity row.

    Lookup precedence:
    1. ``(kind, primary_identifier_scheme, primary_identifier)`` if both are set;
    2. ``(kind, canonical_name)`` otherwise.
    """
    try:
        with get_session() as session:
            row: EntityRow | None = None
            if primary_identifier and primary_identifier_scheme:
                row = session.execute(
                    select(EntityRow)
                    .where(EntityRow.kind == kind)
                    .where(
                        EntityRow.primary_identifier_scheme == primary_identifier_scheme
                    )
                    .where(EntityRow.primary_identifier == primary_identifier)
                    .limit(1)
                ).scalar_one_or_none()
            if row is None:
                row = session.execute(
                    select(EntityRow)
                    .where(EntityRow.kind == kind)
                    .where(EntityRow.canonical_name == canonical_name)
                    .limit(1)
                ).scalar_one_or_none()

            now = datetime.utcnow()
            if row is None:
                row = EntityRow(
                    kind=kind,
                    canonical_name=canonical_name,
                    short_name=short_name,
                    primary_identifier=primary_identifier,
                    primary_identifier_scheme=primary_identifier_scheme,
                    description=description,
                    attributes=dict(attributes or {}),
                    tags=list(tags or []),
                    confidence=confidence,
                    source_dataset=source_dataset,
                    source_extractor=source_extractor,
                    instrument_id=instrument_id,
                    issuer_id=issuer_id,
                    parent_id=parent_id,
                    is_canonical=bool(is_canonical) if is_canonical is not None else True,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                session.flush()
            else:
                if short_name:
                    row.short_name = short_name
                if description:
                    row.description = description
                if primary_identifier:
                    row.primary_identifier = primary_identifier
                if primary_identifier_scheme:
                    row.primary_identifier_scheme = primary_identifier_scheme
                if attributes:
                    row.attributes = {**(row.attributes or {}), **attributes}
                if tags:
                    merged = list(set((row.tags or []) + list(tags)))
                    row.tags = merged
                if confidence is not None:
                    row.confidence = confidence
                if source_dataset:
                    row.source_dataset = source_dataset
                if source_extractor:
                    row.source_extractor = source_extractor
                if instrument_id:
                    row.instrument_id = instrument_id
                if issuer_id:
                    row.issuer_id = issuer_id
                if parent_id:
                    row.parent_id = parent_id
                if is_canonical is not None:
                    row.is_canonical = bool(is_canonical)
                row.updated_at = now
                session.add(row)
            session.flush()
            payload = _row_to_dict(row)
            if graph := _graph_store():
                graph.upsert_entity(payload)
            return payload
    except SQLAlchemyError as exc:
        logger.warning("upsert_entity skipped (%s)", exc)
        return None


def link_entity_identifier(
    *,
    entity_id: str,
    scheme: str,
    value: str,
    source: str | None = None,
    confidence: float | None = None,
    valid_from: Any = None,
    valid_to: Any = None,
) -> dict[str, Any] | None:
    """Add an alias to an entity (idempotent on the triple)."""
    try:
        with get_session() as session:
            existing = session.execute(
                select(EntityIdentifier)
                .where(EntityIdentifier.entity_id == entity_id)
                .where(EntityIdentifier.scheme == scheme)
                .where(EntityIdentifier.value == value)
                .limit(1)
            ).scalar_one_or_none()
            if existing is not None:
                payload = _identifier_to_dict(existing)
                if graph := _graph_store():
                    graph.link_identifier(
                        entity_id=entity_id,
                        scheme=scheme,
                        value=value,
                        source=source,
                        confidence=confidence,
                    )
                return payload
            row = EntityIdentifier(
                entity_id=entity_id,
                scheme=scheme,
                value=value,
                source=source,
                confidence=confidence,
                valid_from=_coerce_dt(valid_from),
                valid_to=_coerce_dt(valid_to),
                created_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            payload = _identifier_to_dict(row)
            if graph := _graph_store():
                graph.link_identifier(
                    entity_id=entity_id,
                    scheme=scheme,
                    value=value,
                    source=source,
                    confidence=confidence,
                )
            return payload
    except SQLAlchemyError as exc:
        logger.warning("link_entity_identifier skipped (%s)", exc)
        return None


def add_entity_relation(
    *,
    subject_id: str,
    predicate: str,
    object_id: str,
    confidence: float | None = None,
    provenance: str | None = None,
    properties: dict[str, Any] | None = None,
    valid_from: Any = None,
    valid_to: Any = None,
) -> dict[str, Any] | None:
    try:
        with get_session() as session:
            existing = session.execute(
                select(EntityRelation)
                .where(EntityRelation.subject_id == subject_id)
                .where(EntityRelation.predicate == predicate)
                .where(EntityRelation.object_id == object_id)
                .limit(1)
            ).scalar_one_or_none()
            if existing is not None:
                if confidence is not None:
                    existing.confidence = confidence
                if provenance:
                    existing.provenance = provenance
                if properties:
                    existing.properties = {**(existing.properties or {}), **properties}
                session.add(existing)
                session.flush()
                payload = _relation_to_dict(existing)
                if graph := _graph_store():
                    graph.add_relation(
                        subject_id=subject_id,
                        predicate=predicate,
                        object_id=object_id,
                        confidence=confidence,
                        provenance=provenance,
                        properties=properties,
                    )
                return payload
            row = EntityRelation(
                subject_id=subject_id,
                predicate=predicate,
                object_id=object_id,
                confidence=confidence,
                provenance=provenance,
                properties=dict(properties or {}),
                valid_from=_coerce_dt(valid_from),
                valid_to=_coerce_dt(valid_to),
                created_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            payload = _relation_to_dict(row)
            if graph := _graph_store():
                graph.add_relation(
                    subject_id=subject_id,
                    predicate=predicate,
                    object_id=object_id,
                    confidence=confidence,
                    provenance=provenance,
                    properties=properties,
                )
            return payload
    except SQLAlchemyError as exc:
        logger.warning("add_entity_relation skipped (%s)", exc)
        return None


def attach_entity_to_dataset(
    *,
    entity_id: str,
    dataset_catalog_id: str | None = None,
    dataset_version_id: str | None = None,
    iceberg_identifier: str | None = None,
    row_count: int | None = None,
    coverage_start: Any = None,
    coverage_end: Any = None,
    role: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        with get_session() as session:
            row = EntityDatasetLink(
                entity_id=entity_id,
                dataset_catalog_id=dataset_catalog_id,
                dataset_version_id=dataset_version_id,
                iceberg_identifier=iceberg_identifier,
                row_count=row_count,
                coverage_start=_coerce_dt(coverage_start),
                coverage_end=_coerce_dt(coverage_end),
                role=role,
                meta=dict(meta or {}),
                created_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            payload = {
                "id": row.id,
                "entity_id": row.entity_id,
                "iceberg_identifier": row.iceberg_identifier,
                "role": row.role,
            }
            if graph := _graph_store():
                graph.link_dataset(
                    entity_id=entity_id,
                    dataset_catalog_id=dataset_catalog_id,
                    dataset_version_id=dataset_version_id,
                    iceberg_identifier=iceberg_identifier,
                    row_count=row_count,
                    role=role,
                    meta=meta,
                )
            return payload
    except SQLAlchemyError as exc:
        logger.warning("attach_entity_to_dataset skipped (%s)", exc)
        return None


def get_entity(entity_id: str) -> dict[str, Any] | None:
    if graph := _graph_store():
        row = graph.get_entity(entity_id)
        if row is not None:
            return row
    try:
        with get_session() as session:
            row = session.execute(
                select(EntityRow).where(EntityRow.id == entity_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            return _row_to_dict(row, include_neighbors=True, session=session)
    except SQLAlchemyError as exc:
        logger.warning("get_entity skipped (%s)", exc)
        return None


def list_entities(
    *,
    kind: str | None = None,
    source_dataset: str | None = None,
    limit: int = 100,
    offset: int = 0,
    canonical_only: bool = False,
) -> list[dict[str, Any]]:
    if graph := _graph_store():
        rows = graph.list_entities(
            kind=kind,
            source_dataset=source_dataset,
            limit=limit,
            offset=offset,
            canonical_only=canonical_only,
        )
        if rows:
            return rows
    try:
        with get_session() as session:
            stmt = select(EntityRow)
            if kind:
                stmt = stmt.where(EntityRow.kind == kind)
            if source_dataset:
                stmt = stmt.where(EntityRow.source_dataset == source_dataset)
            if canonical_only:
                stmt = stmt.where(EntityRow.is_canonical.is_(True))
            stmt = stmt.order_by(EntityRow.canonical_name).limit(limit).offset(offset)
            rows = session.execute(stmt).scalars().all()
            return [_row_to_dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("list_entities skipped (%s)", exc)
        return []


def search_entities(
    query: str,
    *,
    kind: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not query or len(query) < 2:
        return []
    if graph := _graph_store():
        rows = graph.search_entities(query, kind=kind, limit=limit)
        if rows:
            return rows
    pattern = f"%{query.lower()}%"
    try:
        with get_session() as session:
            stmt = (
                select(EntityRow)
                .where(
                    or_(
                        EntityRow.canonical_name.ilike(pattern),
                        EntityRow.short_name.ilike(pattern),
                        EntityRow.primary_identifier.ilike(pattern),
                    )
                )
                .limit(limit)
            )
            if kind:
                stmt = stmt.where(EntityRow.kind == kind)
            rows = session.execute(stmt).scalars().all()
            return [_row_to_dict(row) for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("search_entities skipped (%s)", exc)
        return []


def neighbors(entity_id: str, *, depth: int = 1, limit: int = 64) -> dict[str, Any]:
    """Return outgoing + incoming relations for an entity."""
    if graph := _graph_store():
        payload = graph.neighbors(entity_id, depth=depth, limit=limit)
        if payload.get("outgoing") or payload.get("incoming"):
            return payload
    try:
        with get_session() as session:
            outgoing = (
                session.execute(
                    select(EntityRelation)
                    .where(EntityRelation.subject_id == entity_id)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            incoming = (
                session.execute(
                    select(EntityRelation)
                    .where(EntityRelation.object_id == entity_id)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return {
                "entity_id": entity_id,
                "outgoing": [_relation_to_dict(r) for r in outgoing],
                "incoming": [_relation_to_dict(r) for r in incoming],
            }
    except SQLAlchemyError as exc:
        logger.warning("neighbors skipped (%s)", exc)
        return {"entity_id": entity_id, "outgoing": [], "incoming": []}


def entity_graph(
    *,
    root_id: str | None = None,
    query: str | None = None,
    depth: int = 2,
    limit: int = 200,
) -> dict[str, Any]:
    """Return a graph-explorer payload from the configured graph store."""
    if graph := _graph_store():
        payload = graph.graph(root_id=root_id, query=query, depth=depth, limit=limit)
        if payload.get("nodes") or payload.get("error"):
            return payload
    return {"root_id": root_id, "depth": depth, "nodes": [], "edges": []}


def add_annotation(
    *,
    entity_id: str,
    content: str,
    kind: str = "description",
    author: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    citations: list[str] | None = None,
    confidence: float | None = None,
) -> dict[str, Any] | None:
    try:
        with get_session() as session:
            row = EntityAnnotation(
                entity_id=entity_id,
                kind=kind,
                content=content,
                author=author,
                model=model,
                provider=provider,
                citations=list(citations or []),
                confidence=confidence,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            return _annotation_to_dict(row)
    except SQLAlchemyError as exc:
        logger.warning("add_annotation skipped (%s)", exc)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_dict(
    row: EntityRow,
    *,
    include_neighbors: bool = False,
    session: Any = None,
) -> dict[str, Any]:
    out = {
        "id": row.id,
        "kind": row.kind,
        "canonical_name": row.canonical_name,
        "short_name": row.short_name,
        "primary_identifier": row.primary_identifier,
        "primary_identifier_scheme": row.primary_identifier_scheme,
        "instrument_id": row.instrument_id,
        "issuer_id": row.issuer_id,
        "description": row.description,
        "attributes": dict(row.attributes or {}),
        "tags": list(row.tags or []),
        "confidence": row.confidence,
        "source_dataset": row.source_dataset,
        "source_extractor": row.source_extractor,
        "is_canonical": bool(row.is_canonical),
        "parent_id": row.parent_id,
        "created_at": (row.created_at or datetime.utcnow()).isoformat(),
        "updated_at": (row.updated_at or datetime.utcnow()).isoformat(),
    }
    if include_neighbors and session is not None:
        out["identifiers"] = [
            _identifier_to_dict(r)
            for r in session.execute(
                select(EntityIdentifier).where(EntityIdentifier.entity_id == row.id)
            )
            .scalars()
            .all()
        ]
        out["annotations"] = [
            _annotation_to_dict(r)
            for r in session.execute(
                select(EntityAnnotation)
                .where(EntityAnnotation.entity_id == row.id)
                .order_by(EntityAnnotation.created_at.desc())
                .limit(20)
            )
            .scalars()
            .all()
        ]
    return out


def _identifier_to_dict(row: EntityIdentifier) -> dict[str, Any]:
    return {
        "id": row.id,
        "entity_id": row.entity_id,
        "scheme": row.scheme,
        "value": row.value,
        "source": row.source,
        "confidence": row.confidence,
    }


def _relation_to_dict(row: EntityRelation) -> dict[str, Any]:
    return {
        "id": row.id,
        "subject_id": row.subject_id,
        "predicate": row.predicate,
        "object_id": row.object_id,
        "confidence": row.confidence,
        "provenance": row.provenance,
        "properties": dict(row.properties or {}),
    }


def _annotation_to_dict(row: EntityAnnotation) -> dict[str, Any]:
    return {
        "id": row.id,
        "entity_id": row.entity_id,
        "kind": row.kind,
        "content": row.content,
        "author": row.author,
        "model": row.model,
        "provider": row.provider,
        "citations": list(row.citations or []),
        "confidence": row.confidence,
        "created_at": (row.created_at or datetime.utcnow()).isoformat(),
    }


# ---------------------------------------------------------------------------
# Class facade (used by extractors / Dagster assets that want a stateful API)
# ---------------------------------------------------------------------------


class EntityRegistry:
    """Convenience wrapper around the module-level functions.

    Useful for Dagster assets that want one resource handle and to
    accumulate counters (``upserts``, ``identifiers``, ``relations``).
    """

    def __init__(self) -> None:
        self.upserts = 0
        self.identifiers = 0
        self.relations = 0
        self.annotations = 0
        self.attached = 0

    def upsert(self, **kwargs: Any) -> dict[str, Any] | None:
        result = upsert_entity(**kwargs)
        if result:
            self.upserts += 1
        return result

    def link_identifier(self, **kwargs: Any) -> dict[str, Any] | None:
        result = link_entity_identifier(**kwargs)
        if result:
            self.identifiers += 1
        return result

    def add_relation(self, **kwargs: Any) -> dict[str, Any] | None:
        result = add_entity_relation(**kwargs)
        if result:
            self.relations += 1
        return result

    def attach(self, **kwargs: Any) -> dict[str, Any] | None:
        result = attach_entity_to_dataset(**kwargs)
        if result:
            self.attached += 1
        return result

    def annotate(self, **kwargs: Any) -> dict[str, Any] | None:
        result = add_annotation(**kwargs)
        if result:
            self.annotations += 1
        return result

    def upsert_many(self, rows: Iterable[dict[str, Any]]) -> int:
        before = self.upserts
        for entry in rows:
            self.upsert(**entry)
        return self.upserts - before

    def stats(self) -> dict[str, int]:
        return {
            "upserts": self.upserts,
            "identifiers": self.identifiers,
            "relations": self.relations,
            "annotations": self.annotations,
            "attached": self.attached,
        }


__all__ = [
    "EntityRegistry",
    "add_annotation",
    "add_entity_relation",
    "attach_entity_to_dataset",
    "entity_graph",
    "get_entity",
    "link_entity_identifier",
    "list_entities",
    "neighbors",
    "search_entities",
    "upsert_entity",
]
