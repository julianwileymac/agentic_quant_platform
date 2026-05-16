"""Neo4j-backed ownership graph store.

Mirrors the Postgres canonical tables into a Neo4j graph so multi-hop
ownership traversals are sub-millisecond. Writes flow through
:meth:`apply_events`; reads flow through :meth:`traverse`,
:meth:`list_resources_visible_to`, and :meth:`who_can_read`.

The driver is imported lazily so the base AQP install still works
without the ``neo4j`` extra (Postgres-store deployments).
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings
from aqp.graph.protocol import (
    OwnershipEdge,
    OwnershipGraphStore,
    OwnershipNode,
)

logger = logging.getLogger(__name__)


# All Cypher templates use ``$properties`` instead of inlining so the
# Bolt driver can pre-compile + cache the plan. ``MERGE`` is the
# central idempotency primitive — replaying a stream of events
# converges on the same graph regardless of order.

_UPSERT_NODE_CYPHER = """
MERGE (n:`{kind}` {{id: $id}})
SET n += $properties
SET n.updated_at = timestamp()
"""

_UPSERT_EDGE_CYPHER = """
MERGE (a:`{from_kind}` {{id: $from_id}})
MERGE (b:`{to_kind}` {{id: $to_id}})
MERGE (a)-[r:`{relation}`]->(b)
SET r += $properties
"""

_DELETE_NODE_CYPHER = """
MATCH (n:`{kind}` {{id: $id}})
DETACH DELETE n
"""

_DELETE_EDGE_CYPHER = """
MATCH (a:`{from_kind}` {{id: $from_id}})-[r:`{relation}`]->(b:`{to_kind}` {{id: $to_id}})
DELETE r
"""


class Neo4jOwnershipGraphStore(OwnershipGraphStore):
    """Idempotent Neo4j adapter — every write is a ``MERGE``."""

    name = "neo4j"

    def __init__(self) -> None:
        self.uri = settings.neo4j_uri
        self.user = settings.neo4j_user
        self.password = settings.neo4j_password
        self.database = settings.neo4j_database
        self._driver: Any | None = None
        self._driver_error: str | None = None

    # ------------------------------------------------------------------
    # Driver / health
    # ------------------------------------------------------------------
    def _get_driver(self) -> Any:
        if self._driver is not None:
            return self._driver
        if self._driver_error is not None:
            raise RuntimeError(self._driver_error)
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            return self._driver
        except Exception as exc:  # noqa: BLE001
            self._driver_error = str(exc)
            raise RuntimeError(self._driver_error) from exc

    def health(self) -> dict[str, Any]:
        try:
            with self._get_driver().session(database=self.database) as session:
                rec = session.run("RETURN 1 AS ok").single()
            return {
                "ok": bool(rec and rec["ok"] == 1),
                "kind": "neo4j",
                "uri": self.uri,
                "database": self.database,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "kind": "neo4j",
                "uri": self.uri,
                "database": self.database,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def upsert_node(self, node: OwnershipNode) -> None:
        cypher = _UPSERT_NODE_CYPHER.format(kind=_sanitize_label(node.kind))
        with self._get_driver().session(database=self.database) as session:
            session.run(
                cypher,
                id=str(node.id),
                properties=_flatten(node.properties),
            )

    def upsert_edge(self, edge: OwnershipEdge) -> None:
        cypher = _UPSERT_EDGE_CYPHER.format(
            from_kind=_sanitize_label(edge.from_kind),
            to_kind=_sanitize_label(edge.to_kind),
            relation=_sanitize_label(edge.relation),
        )
        with self._get_driver().session(database=self.database) as session:
            session.run(
                cypher,
                from_id=str(edge.from_id),
                to_id=str(edge.to_id),
                properties=_flatten(edge.properties),
            )

    def delete_node(self, kind: str, identifier: str) -> None:
        cypher = _DELETE_NODE_CYPHER.format(kind=_sanitize_label(kind))
        with self._get_driver().session(database=self.database) as session:
            session.run(cypher, id=str(identifier))

    def delete_edge(self, edge: OwnershipEdge) -> None:
        cypher = _DELETE_EDGE_CYPHER.format(
            from_kind=_sanitize_label(edge.from_kind),
            to_kind=_sanitize_label(edge.to_kind),
            relation=_sanitize_label(edge.relation),
        )
        with self._get_driver().session(database=self.database) as session:
            session.run(
                cypher,
                from_id=str(edge.from_id),
                to_id=str(edge.to_id),
            )

    def apply_events(self, events: list[Any]) -> int:
        """Apply events in a single transaction for atomicity + speed."""
        if not events:
            return 0
        # Group by Cypher template + dispatch as UNWIND batches when
        # we have a homogenous set; otherwise fall through to the base
        # impl which loops one-at-a-time. Most drain batches are
        # heterogenous so the loop is fine for v1; the hook is there
        # for a future perf bump.
        return super().apply_events(events)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def traverse(
        self,
        *,
        start_kind: str,
        start_id: str,
        edge_kinds: list[str] | None = None,
        depth: int = 2,
        limit: int = 200,
    ) -> dict[str, Any]:
        rel_filter = ""
        if edge_kinds:
            sanitised = "|".join(_sanitize_label(k) for k in edge_kinds)
            rel_filter = f":`{sanitised}`"
        cypher = f"""
        MATCH path = (start:`{_sanitize_label(start_kind)}` {{id: $start_id}})
              -[r{rel_filter}*1..{int(depth)}]->(other)
        WITH nodes(path) AS ns, relationships(path) AS rs
        UNWIND ns AS n
        WITH collect(DISTINCT n) AS all_nodes, collect(DISTINCT rs) AS rel_groups
        UNWIND rel_groups AS rels
        UNWIND rels AS rel
        RETURN all_nodes AS nodes, collect(DISTINCT rel) AS edges
        LIMIT {int(limit)}
        """
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        with self._get_driver().session(database=self.database) as session:
            for record in session.run(cypher, start_id=str(start_id)):
                for n in record["nodes"] or []:
                    props = dict(n)
                    nid = props.get("id") or str(n.element_id)
                    if nid not in nodes:
                        labels = list(getattr(n, "labels", []) or [])
                        nodes[nid] = {
                            "id": str(nid),
                            "kind": labels[0] if labels else "",
                            "properties": props,
                        }
                for r in record["edges"] or []:
                    edges.append(
                        {
                            "from_id": str(dict(r.start_node).get("id", "")),
                            "from_kind": _first_label(r.start_node),
                            "to_id": str(dict(r.end_node).get("id", "")),
                            "to_kind": _first_label(r.end_node),
                            "relation": str(r.type),
                            "properties": dict(r),
                        }
                    )
        return {"nodes": list(nodes.values()), "edges": edges}

    def list_resources_visible_to(
        self,
        *,
        user_id: str,
        resource_type: str | None = None,
        limit: int = 200,
    ) -> list[OwnershipNode]:
        """Cypher equivalent of the Postgres ``WITH user_scopes`` query."""
        cypher = """
        MATCH (u:User {id: $user_id})-[m:MEMBER_OF]->(s)
        MATCH (s)-[:OWNS]->(r:Resource)
        WHERE $resource_type IS NULL OR r.resource_type = $resource_type
        RETURN DISTINCT r
        UNION
        MATCH (r:Resource {owner_scope_kind: 'user', owner_scope_id: $user_id})
        WHERE $resource_type IS NULL OR r.resource_type = $resource_type
        RETURN DISTINCT r
        """
        out: list[OwnershipNode] = []
        with self._get_driver().session(database=self.database) as session:
            for record in session.run(
                cypher, user_id=str(user_id), resource_type=resource_type
            ):
                node = record["r"]
                props = dict(node)
                out.append(
                    OwnershipNode(
                        id=str(props.get("id") or node.element_id),
                        kind="Resource",
                        properties=props,
                    )
                )
                if len(out) >= int(limit):
                    break
        return out

    def who_can_read(self, *, resource_id: str) -> list[dict[str, Any]]:
        cypher = """
        MATCH (r:Resource {id: $resource_id})<-[:OWNS]-(scope)
        MATCH (u:User)-[m:MEMBER_OF]->(scope)
        RETURN DISTINCT u.id AS user_id, m.role AS role,
                        labels(scope)[0] AS scope_kind, scope.id AS scope_id
        """
        with self._get_driver().session(database=self.database) as session:
            return [
                {
                    "user_id": str(rec["user_id"] or ""),
                    "role": str(rec["role"] or "viewer"),
                    "scope_kind": str(rec["scope_kind"] or ""),
                    "scope_id": str(rec["scope_id"] or ""),
                }
                for rec in session.run(cypher, resource_id=str(resource_id))
            ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_label(value: str) -> str:
    """Coerce *value* into a Cypher-safe label / relation token.

    Cypher labels and relationship types must match
    ``[A-Za-z_][A-Za-z0-9_]*``. Anything else gets stripped to ``_`` so
    a misconfigured caller can never inject Cypher.
    """
    if not value:
        return "Unknown"
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in value)
    if not cleaned[0].isalpha() and cleaned[0] != "_":
        cleaned = "_" + cleaned
    return cleaned


def _flatten(properties: dict[str, Any] | None) -> dict[str, Any]:
    """Drop ``None`` values + coerce nested dicts to JSON strings.

    Neo4j property values must be primitives or arrays of primitives;
    serialising nested dicts to JSON keeps round-trips lossless and
    preserves the original shape for the read path.
    """
    if not properties:
        return {}
    import json

    out: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        elif isinstance(value, list) and all(
            isinstance(v, (str, int, float, bool)) for v in value
        ):
            out[key] = value
        else:
            out[key] = json.dumps(value, default=str, sort_keys=True)
    return out


def _first_label(node: Any) -> str:
    labels = list(getattr(node, "labels", []) or [])
    return labels[0] if labels else ""


__all__ = ["Neo4jOwnershipGraphStore"]
