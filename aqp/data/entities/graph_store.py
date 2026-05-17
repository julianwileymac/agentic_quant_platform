"""Graph-store abstraction for the entity registry.

The Postgres tables remain the compatibility system of record for existing
routes. This module provides the graph-first interface used when
``AQP_GRAPH_STORE=neo4j`` is enabled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from aqp.config import settings


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    kind: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "meta": dict(self.meta or {}),
        }


@dataclass(frozen=True)
class GraphEdge:
    from_id: str
    to_id: str
    relationship_type: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "relationship_type": self.relationship_type,
            "meta": dict(self.meta or {}),
        }


class EntityGraphStore(Protocol):
    def health(self) -> dict[str, Any]:
        ...

    def upsert_entity(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        ...

    def link_identifier(
        self,
        *,
        entity_id: str,
        scheme: str,
        value: str,
        source: str | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any] | None:
        ...

    def add_relation(
        self,
        *,
        subject_id: str,
        predicate: str,
        object_id: str,
        confidence: float | None = None,
        provenance: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        ...

    def link_dataset(
        self,
        *,
        entity_id: str,
        dataset_catalog_id: str | None = None,
        dataset_version_id: str | None = None,
        iceberg_identifier: str | None = None,
        row_count: int | None = None,
        role: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        ...

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        ...

    def list_entities(
        self,
        *,
        kind: str | None = None,
        source_dataset: str | None = None,
        limit: int = 100,
        offset: int = 0,
        canonical_only: bool = False,
    ) -> list[dict[str, Any]]:
        ...

    def search_entities(
        self,
        query: str,
        *,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        ...

    def neighbors(self, entity_id: str, *, depth: int = 1, limit: int = 64) -> dict[str, Any]:
        ...

    def graph(
        self,
        *,
        root_id: str | None = None,
        query: str | None = None,
        depth: int = 2,
        limit: int = 200,
    ) -> dict[str, Any]:
        ...


_STORE: EntityGraphStore | None = None


def graph_store_enabled() -> bool:
    return str(settings.graph_store or "").lower() == "neo4j"


def get_graph_store() -> EntityGraphStore | None:
    """Return the configured graph store, or ``None`` when Postgres-only mode is active."""
    global _STORE
    if not graph_store_enabled():
        return None
    if _STORE is None:
        from aqp.data.entities.neo4j_store import Neo4jEntityGraphStore

        _STORE = Neo4jEntityGraphStore()
    return _STORE


def reset_graph_store_for_tests() -> None:
    global _STORE
    _STORE = None


__all__ = [
    "EntityGraphStore",
    "GraphEdge",
    "GraphNode",
    "get_graph_store",
    "graph_store_enabled",
    "reset_graph_store_for_tests",
]
