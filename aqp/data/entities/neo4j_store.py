"""Neo4j-backed entity graph store."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.utcnow().isoformat()


def _coerce_node(raw: Any) -> dict[str, Any]:
    data = dict(raw or {})
    attributes = data.get("attributes")
    if attributes is None and data.get("attributes_json"):
        try:
            attributes = json.loads(str(data.get("attributes_json") or "{}"))
        except ValueError:
            attributes = {}
    return {
        "id": str(data.get("id") or ""),
        "kind": str(data.get("kind") or data.get("label") or "entity"),
        "canonical_name": data.get("canonical_name") or data.get("name") or data.get("id"),
        "short_name": data.get("short_name"),
        "primary_identifier": data.get("primary_identifier"),
        "primary_identifier_scheme": data.get("primary_identifier_scheme"),
        "description": data.get("description"),
        "tags": list(data.get("tags") or []),
        "confidence": data.get("confidence"),
        "source_dataset": data.get("source_dataset"),
        "source_extractor": data.get("source_extractor"),
        "instrument_id": data.get("instrument_id"),
        "issuer_id": data.get("issuer_id"),
        "parent_id": data.get("parent_id"),
        "attributes": dict(attributes or {}),
        "is_canonical": bool(data.get("is_canonical", True)),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }


def _graph_node(raw: Any) -> dict[str, Any]:
    raw_data = dict(raw or {})
    if not raw_data.get("id") and raw_data.get("scheme") and raw_data.get("value"):
        node_id = _node_id(raw)
        return {
            "id": node_id,
            "label": f"{raw_data.get('scheme')}:{raw_data.get('value')}",
            "kind": "identifier",
            "meta": raw_data,
        }
    data = _coerce_node(raw)
    label = str(data.get("canonical_name") or data.get("primary_identifier") or data["id"])
    return {
        "id": data["id"],
        "label": label,
        "kind": str(data.get("kind") or "entity"),
        "meta": data,
    }


def _node_id(raw: Any) -> str:
    data = dict(raw or {})
    if data.get("id"):
        return str(data["id"])
    if data.get("scheme") and data.get("value"):
        return f"identifier:{data['scheme']}:{data['value']}"
    return str(data.get("name") or data.get("label") or "")


class Neo4jEntityGraphStore:
    """Small Neo4j adapter using lazy imports so the base install still works."""

    def __init__(self) -> None:
        self.uri = settings.neo4j_uri
        self.user = settings.neo4j_user
        self.password = settings.neo4j_password
        self.database = settings.neo4j_database
        self._driver: Any | None = None
        self._driver_error: str | None = None

    def _get_driver(self) -> Any:
        if self._driver is not None:
            return self._driver
        if self._driver_error:
            raise RuntimeError(self._driver_error)
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            return self._driver
        except Exception as exc:  # noqa: BLE001
            self._driver_error = str(exc)
            raise RuntimeError(self._driver_error) from exc

    def _execute_read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def _execute_write(self, query: str, **params: Any) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def health(self) -> dict[str, Any]:
        try:
            rows = self._execute_read("RETURN 1 AS ok")
            return {
                "ok": bool(rows and rows[0].get("ok") == 1),
                "uri": self.uri,
                "database": self.database,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "uri": self.uri, "database": self.database, "error": str(exc)}

    def upsert_entity(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not payload.get("id"):
            return None
        props = {
            "id": str(payload["id"]),
            "kind": str(payload.get("kind") or "entity"),
            "canonical_name": str(payload.get("canonical_name") or payload["id"]),
            "short_name": payload.get("short_name"),
            "primary_identifier": payload.get("primary_identifier"),
            "primary_identifier_scheme": payload.get("primary_identifier_scheme"),
            "description": payload.get("description"),
            "tags": list(payload.get("tags") or []),
            "confidence": payload.get("confidence"),
            "source_dataset": payload.get("source_dataset"),
            "source_extractor": payload.get("source_extractor"),
            "instrument_id": payload.get("instrument_id"),
            "issuer_id": payload.get("issuer_id"),
            "parent_id": payload.get("parent_id"),
            "attributes_json": json.dumps(dict(payload.get("attributes") or {}), sort_keys=True),
            "is_canonical": bool(payload.get("is_canonical", True)),
            "updated_at": _now(),
        }
        props["created_at"] = payload.get("created_at") or props["updated_at"]
        try:
            rows = self._execute_write(
                """
                MERGE (e:Entity {id: $id})
                ON CREATE SET e.created_at = $props.created_at
                SET e += $props
                RETURN e AS entity
                """,
                id=props["id"],
                props=props,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j upsert_entity failed: %s", exc)
            return None
        return _coerce_node(rows[0].get("entity")) if rows else None

    def link_identifier(
        self,
        *,
        entity_id: str,
        scheme: str,
        value: str,
        source: str | None = None,
        confidence: float | None = None,
    ) -> dict[str, Any] | None:
        try:
            self._execute_write(
                """
                MATCH (e:Entity {id: $entity_id})
                MERGE (i:Identifier {scheme: $scheme, value: $value})
                SET i.source = coalesce($source, i.source),
                    i.confidence = coalesce($confidence, i.confidence),
                    i.updated_at = $updated_at
                MERGE (e)-[r:HAS_IDENTIFIER]->(i)
                SET r.source = coalesce($source, r.source),
                    r.confidence = coalesce($confidence, r.confidence)
                RETURN i
                """,
                entity_id=entity_id,
                scheme=scheme,
                value=value,
                source=source,
                confidence=confidence,
                updated_at=_now(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j link_identifier failed: %s", exc)
            return None
        return {"entity_id": entity_id, "scheme": scheme, "value": value, "source": source}

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
        try:
            self._execute_write(
                """
                MATCH (s:Entity {id: $subject_id})
                MATCH (o:Entity {id: $object_id})
                MERGE (s)-[r:RELATES_TO {predicate: $predicate}]->(o)
                SET r.confidence = coalesce($confidence, r.confidence),
                    r.provenance = coalesce($provenance, r.provenance),
                    r.properties_json = $properties_json,
                    r.updated_at = $updated_at
                RETURN r
                """,
                subject_id=subject_id,
                object_id=object_id,
                predicate=predicate,
                confidence=confidence,
                provenance=provenance,
                properties_json=json.dumps(dict(properties or {}), sort_keys=True),
                updated_at=_now(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j add_relation failed: %s", exc)
            return None
        return {
            "subject_id": subject_id,
            "predicate": predicate,
            "object_id": object_id,
            "confidence": confidence,
            "provenance": provenance,
            "properties": dict(properties or {}),
        }

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
        dataset_id = dataset_catalog_id or iceberg_identifier
        if not dataset_id:
            return None
        props = {
            "id": str(dataset_id),
            "dataset_catalog_id": dataset_catalog_id,
            "dataset_version_id": dataset_version_id,
            "iceberg_identifier": iceberg_identifier,
            "row_count": row_count,
            "role": role,
            "meta_json": json.dumps(dict(meta or {}), sort_keys=True),
            "updated_at": _now(),
        }
        try:
            self._execute_write(
                """
                MATCH (e:Entity {id: $entity_id})
                MERGE (d:Dataset {id: $dataset_id})
                SET d += $props
                MERGE (e)-[r:COVERS]->(d)
                SET r.role = coalesce($role, r.role),
                    r.row_count = coalesce($row_count, r.row_count),
                    r.updated_at = $updated_at
                RETURN d
                """,
                entity_id=entity_id,
                dataset_id=str(dataset_id),
                props=props,
                role=role,
                row_count=row_count,
                updated_at=props["updated_at"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j link_dataset failed: %s", exc)
            return None
        return {"entity_id": entity_id, **props}

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        try:
            rows = self._execute_read(
                """
                MATCH (e:Entity {id: $entity_id})
                OPTIONAL MATCH (e)-[:HAS_IDENTIFIER]->(i:Identifier)
                RETURN e AS entity, collect(i) AS identifiers
                LIMIT 1
                """,
                entity_id=entity_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j get_entity failed: %s", exc)
            return None
        if not rows:
            return None
        out = _coerce_node(rows[0].get("entity"))
        out["identifiers"] = [dict(i or {}) for i in rows[0].get("identifiers") or []]
        out["annotations"] = []
        return out

    def list_entities(
        self,
        *,
        kind: str | None = None,
        source_dataset: str | None = None,
        limit: int = 100,
        offset: int = 0,
        canonical_only: bool = False,
    ) -> list[dict[str, Any]]:
        where = ["($kind IS NULL OR e.kind = $kind)", "($source_dataset IS NULL OR e.source_dataset = $source_dataset)"]
        if canonical_only:
            where.append("coalesce(e.is_canonical, true) = true")
        try:
            rows = self._execute_read(
                f"""
                MATCH (e:Entity)
                WHERE {" AND ".join(where)}
                RETURN e AS entity
                ORDER BY e.canonical_name
                SKIP $offset LIMIT $limit
                """,
                kind=kind,
                source_dataset=source_dataset,
                offset=max(0, int(offset)),
                limit=max(1, int(limit)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j list_entities failed: %s", exc)
            return []
        return [_coerce_node(row.get("entity")) for row in rows]

    def search_entities(
        self,
        query: str,
        *,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        q = str(query or "").lower()
        if len(q) < 2:
            return []
        try:
            rows = self._execute_read(
                """
                MATCH (e:Entity)
                WHERE ($kind IS NULL OR e.kind = $kind)
                  AND (
                    toLower(coalesce(e.canonical_name, "")) CONTAINS $q OR
                    toLower(coalesce(e.short_name, "")) CONTAINS $q OR
                    toLower(coalesce(e.primary_identifier, "")) CONTAINS $q
                  )
                RETURN e AS entity
                ORDER BY e.canonical_name
                LIMIT $limit
                """,
                q=q,
                kind=kind,
                limit=max(1, int(limit)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j search_entities failed: %s", exc)
            return []
        return [_coerce_node(row.get("entity")) for row in rows]

    def neighbors(self, entity_id: str, *, depth: int = 1, limit: int = 64) -> dict[str, Any]:
        depth = max(1, min(int(depth), 3))
        try:
            rows = self._execute_read(
                f"""
                MATCH (e:Entity {{id: $entity_id}})-[r*1..{depth}]-(n)
                RETURN e AS root, n AS neighbor, r AS rels
                LIMIT $limit
                """,
                entity_id=entity_id,
                limit=max(1, int(limit)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j neighbors failed: %s", exc)
            return {"entity_id": entity_id, "outgoing": [], "incoming": [], "error": str(exc)}
        outgoing: list[dict[str, Any]] = []
        for row in rows:
            neighbor = _coerce_node(row.get("neighbor"))
            rels = row.get("rels") or []
            predicate = "RELATED"
            if rels:
                predicate = dict(rels[-1] or {}).get("predicate") or getattr(rels[-1], "type", "RELATED")
            outgoing.append(
                {
                    "subject_id": entity_id,
                    "predicate": predicate,
                    "object_id": neighbor["id"],
                    "properties": {"neighbor": neighbor},
                }
            )
        return {"entity_id": entity_id, "outgoing": outgoing, "incoming": []}

    def graph(
        self,
        *,
        root_id: str | None = None,
        query: str | None = None,
        depth: int = 2,
        limit: int = 200,
    ) -> dict[str, Any]:
        depth = max(1, min(int(depth), 4))
        limit = max(1, min(int(limit), 500))
        try:
            if root_id:
                rows = self._execute_read(
                    f"""
                    MATCH p=(root:Entity {{id: $root_id}})-[*0..{depth}]-(n)
                    WITH collect(p) AS paths
                    UNWIND paths AS p
                    UNWIND nodes(p) AS node
                    WITH paths, collect(DISTINCT node) AS nodes
                    UNWIND paths AS p
                    UNWIND relationships(p) AS rel
                    RETURN nodes, collect(DISTINCT rel) AS rels
                    LIMIT 1
                    """,
                    root_id=root_id,
                )
            else:
                q = str(query or "").lower()
                rows = self._execute_read(
                    """
                    MATCH (n:Entity)
                    WHERE $q = "" OR toLower(coalesce(n.canonical_name, "")) CONTAINS $q
                    OPTIONAL MATCH (n)-[r]-(m)
                    RETURN (collect(DISTINCT n) + collect(DISTINCT m))[0..$limit] AS nodes,
                           collect(DISTINCT r)[0..$limit] AS rels
                    """,
                    q=q,
                    limit=limit,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j graph failed: %s", exc)
            return {"root_id": root_id, "depth": depth, "nodes": [], "edges": [], "error": str(exc)}

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        if rows:
            for node in rows[0].get("nodes") or []:
                gnode = _graph_node(node)
                if gnode["id"]:
                    nodes[gnode["id"]] = gnode
            for rel in rows[0].get("rels") or []:
                try:
                    start_id = _node_id(rel.start_node)
                    end_id = _node_id(rel.end_node)
                    if not start_id or not end_id:
                        continue
                    rtype = dict(rel).get("predicate") or rel.type
                    edges.append(
                        {
                            "from_id": start_id,
                            "to_id": end_id,
                            "relationship_type": str(rtype),
                            "meta": dict(rel),
                        }
                    )
                except Exception:
                    continue
        return {
            "root_id": root_id,
            "depth": depth,
            "nodes": list(nodes.values())[:limit],
            "edges": edges[:limit],
        }


__all__ = ["Neo4jEntityGraphStore"]
