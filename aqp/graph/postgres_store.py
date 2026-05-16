"""Postgres-only ownership graph implementation.

Used in two modes:

- **Local / unit tests**: stays the only store when
  ``AQP_OWNERSHIP_GRAPH_STORE=postgres`` so the test loop never needs
  a Neo4j instance.
- **Bootstrap / drift recovery**: the
  :func:`aqp.tasks.ownership_tasks.full_resync` task materialises
  every node + edge from this store and replays it into the Neo4j
  store, healing any events lost between an outage and recovery.

Writes here are **no-ops** — the canonical writes already happened
when the underlying tenancy / resource / experiment row committed.
Reads use ``WITH RECURSIVE`` Postgres queries over the canonical
tables.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from aqp.graph.protocol import (
    OwnershipEdge,
    OwnershipGraphStore,
    OwnershipNode,
)
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)


class PostgresOwnershipGraphStore(OwnershipGraphStore):
    """Read-through view over the canonical tenancy / resource / experiment rows."""

    name = "postgres"

    # --- writes are no-ops ----------------------------------------------
    def upsert_node(self, node: OwnershipNode) -> None:  # noqa: D401
        # Writes land on the canonical tables; nothing to do here.
        return

    def upsert_edge(self, edge: OwnershipEdge) -> None:  # noqa: D401
        return

    def delete_node(self, kind: str, identifier: str) -> None:  # noqa: D401
        return

    def delete_edge(self, edge: OwnershipEdge) -> None:  # noqa: D401
        return

    # --- introspection ---------------------------------------------------
    def health(self) -> dict[str, Any]:
        try:
            with get_session() as session:
                session.execute(text("SELECT 1"))
            return {"ok": True, "kind": "postgres"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "kind": "postgres", "error": str(exc)}

    # --- queries ---------------------------------------------------------
    def traverse(
        self,
        *,
        start_kind: str,
        start_id: str,
        edge_kinds: list[str] | None = None,
        depth: int = 2,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Walk outward from ``(start_kind, start_id)`` collecting nodes + edges.

        We materialise the relevant subgraph by issuing a small
        sequence of fan-out queries — one hop per ``depth`` step. This
        is intentionally simple: the Postgres store is the bootstrap /
        unit-test path; high-performance traversal is the Neo4j store's
        job. A future revision can replace this with a single
        ``WITH RECURSIVE`` query over a unified edges view if perf
        matters here.
        """
        edge_filter = {k.upper() for k in (edge_kinds or [])}
        nodes: dict[tuple[str, str], OwnershipNode] = {}
        edges: list[OwnershipEdge] = []

        frontier: list[tuple[str, str]] = [(start_kind, start_id)]
        seen: set[tuple[str, str]] = set(frontier)

        with get_session() as session:
            for _ in range(max(1, int(depth))):
                next_frontier: list[tuple[str, str]] = []
                for kind, identifier in frontier:
                    for edge in self._adjacent_edges(session, kind, identifier):
                        if edge_filter and edge.relation not in edge_filter:
                            continue
                        edges.append(edge)
                        nb_key = (edge.to_kind, edge.to_id)
                        if nb_key not in seen:
                            seen.add(nb_key)
                            next_frontier.append(nb_key)
                        if len(edges) >= limit:
                            break
                    if len(edges) >= limit:
                        break
                frontier = next_frontier
                if not frontier or len(edges) >= limit:
                    break

            for kind, identifier in seen:
                node = self._fetch_node(session, kind, identifier)
                if node is not None:
                    nodes[(kind, identifier)] = node

        return {
            "nodes": [
                {"id": n.id, "kind": n.kind, "properties": n.properties}
                for n in nodes.values()
            ],
            "edges": [
                {
                    "from_id": e.from_id,
                    "from_kind": e.from_kind,
                    "to_id": e.to_id,
                    "to_kind": e.to_kind,
                    "relation": e.relation,
                    "properties": e.properties,
                }
                for e in edges
            ],
        }

    def list_resources_visible_to(
        self,
        *,
        user_id: str,
        resource_type: str | None = None,
        limit: int = 200,
    ) -> list[OwnershipNode]:
        """Return every Resource the user can see via the membership graph.

        Visibility model implemented inline:

        - ``owner_scope_kind='user'`` AND ``owner_scope_id=user_id`` -> visible
        - ``owner_scope_kind='team'`` AND user is member of that team -> visible
        - ``owner_scope_kind='workspace'`` AND user has any membership in the
          workspace OR the workspace visibility is 'org' AND user is in the org
        - ``owner_scope_kind='project'`` AND user is project member or
          inherits via workspace
        - ``owner_scope_kind='organization'`` AND user is in the org -> visible
        """
        sql = """
        WITH user_scopes AS (
            SELECT 'organization' AS scope_kind, scope_id
              FROM memberships
             WHERE user_id = :user_id AND scope_kind = 'org'
            UNION ALL
            SELECT 'team', scope_id
              FROM memberships
             WHERE user_id = :user_id AND scope_kind = 'team'
            UNION ALL
            SELECT 'workspace', scope_id
              FROM memberships
             WHERE user_id = :user_id AND scope_kind = 'workspace'
            UNION ALL
            SELECT 'project', scope_id
              FROM memberships
             WHERE user_id = :user_id AND scope_kind = 'project'
            UNION ALL
            SELECT 'user', :user_id
        )
        SELECT r.id, r.name, r.slug, r.resource_type, r.uri,
               r.owner_scope_kind, r.owner_scope_id, r.workspace_id,
               r.project_id, r.visibility, r.meta, r.tags
          FROM aqp_resources r
          JOIN user_scopes us
            ON us.scope_kind = r.owner_scope_kind
           AND us.scope_id = r.owner_scope_id
         WHERE (:resource_type IS NULL OR r.resource_type = :resource_type)
         ORDER BY r.updated_at DESC
         LIMIT :limit
        """
        out: list[OwnershipNode] = []
        with get_session() as session:
            rows = session.execute(
                text(sql),
                {
                    "user_id": user_id,
                    "resource_type": resource_type,
                    "limit": int(limit),
                },
            ).mappings().all()
        for row in rows:
            props = dict(row)
            out.append(
                OwnershipNode(
                    id=str(row["id"]),
                    kind="Resource",
                    properties=props,
                )
            )
        return out

    def who_can_read(self, *, resource_id: str) -> list[dict[str, Any]]:
        """Materialise the inverse: from a resource, list every user with access."""
        sql = """
        WITH res AS (
            SELECT owner_scope_kind, owner_scope_id, workspace_id, project_id
              FROM aqp_resources WHERE id = :resource_id
        )
        SELECT m.user_id, m.role, m.scope_kind, m.scope_id
          FROM memberships m, res r
         WHERE (m.scope_kind, m.scope_id) IN (
                    SELECT r.owner_scope_kind, r.owner_scope_id
                    UNION ALL
                    SELECT 'workspace', r.workspace_id WHERE r.workspace_id IS NOT NULL
                    UNION ALL
                    SELECT 'project', r.project_id WHERE r.project_id IS NOT NULL
                )
        """
        with get_session() as session:
            rows = session.execute(text(sql), {"resource_id": resource_id}).mappings().all()
        return [
            {
                "user_id": str(row["user_id"]),
                "role": str(row["role"]),
                "scope_kind": str(row["scope_kind"]),
                "scope_id": str(row["scope_id"]),
            }
            for row in rows
        ]

    # --- helpers ---------------------------------------------------------
    def _fetch_node(
        self, session: Any, kind: str, identifier: str
    ) -> OwnershipNode | None:
        """Pull node properties from the canonical table for *kind*."""
        table_map: dict[str, tuple[str, str]] = {
            "Organization": ("organizations", "id, slug, name"),
            "Team": ("teams", "id, slug, name, org_id"),
            "User": ("users", "id, email, display_name, auth_subject"),
            "Workspace": ("workspaces", "id, slug, name, org_id, visibility"),
            "Project": ("projects", "id, slug, name, workspace_id"),
            "Lab": ("labs", "id, slug, name, workspace_id"),
            "Experiment": ("aqp_experiments", "id, slug, name, kind, status, project_id"),
            "Test": ("aqp_tests", "id, slug, name, assertion_kind, passed, experiment_id"),
            "Resource": (
                "aqp_resources",
                "id, slug, name, resource_type, owner_scope_kind, owner_scope_id",
            ),
        }
        spec = table_map.get(kind)
        if not spec:
            return OwnershipNode(id=identifier, kind=kind, properties={})
        table, cols = spec
        row = session.execute(
            text(f"SELECT {cols} FROM {table} WHERE id = :id"), {"id": identifier}
        ).mappings().first()
        if not row:
            return None
        return OwnershipNode(
            id=identifier,
            kind=kind,
            properties=dict(row),
        )

    def _adjacent_edges(
        self, session: Any, kind: str, identifier: str
    ) -> list[OwnershipEdge]:
        """Outgoing edges from a node. Per-kind switch — keep simple."""
        edges: list[OwnershipEdge] = []
        if kind == "Organization":
            for row in session.execute(
                text("SELECT id FROM teams WHERE org_id = :id"), {"id": identifier}
            ).mappings():
                edges.append(
                    OwnershipEdge(
                        from_id=identifier,
                        from_kind="Organization",
                        to_id=str(row["id"]),
                        to_kind="Team",
                        relation="HAS_TEAM",
                    )
                )
            for row in session.execute(
                text("SELECT id FROM workspaces WHERE org_id = :id"), {"id": identifier}
            ).mappings():
                edges.append(
                    OwnershipEdge(
                        from_id=identifier,
                        from_kind="Organization",
                        to_id=str(row["id"]),
                        to_kind="Workspace",
                        relation="HAS_WORKSPACE",
                    )
                )
        elif kind == "Team":
            for row in session.execute(
                text(
                    "SELECT user_id, role FROM memberships "
                    "WHERE scope_kind = 'team' AND scope_id = :id"
                ),
                {"id": identifier},
            ).mappings():
                edges.append(
                    OwnershipEdge(
                        from_id=str(row["user_id"]),
                        from_kind="User",
                        to_id=identifier,
                        to_kind="Team",
                        relation="MEMBER_OF",
                        properties={"role": str(row["role"])},
                    )
                )
        elif kind == "Workspace":
            for row in session.execute(
                text("SELECT id FROM projects WHERE workspace_id = :id"),
                {"id": identifier},
            ).mappings():
                edges.append(
                    OwnershipEdge(
                        from_id=identifier,
                        from_kind="Workspace",
                        to_id=str(row["id"]),
                        to_kind="Project",
                        relation="HAS_PROJECT",
                    )
                )
            for row in session.execute(
                text("SELECT id FROM labs WHERE workspace_id = :id"),
                {"id": identifier},
            ).mappings():
                edges.append(
                    OwnershipEdge(
                        from_id=identifier,
                        from_kind="Workspace",
                        to_id=str(row["id"]),
                        to_kind="Lab",
                        relation="HAS_LAB",
                    )
                )
        elif kind == "Project":
            for row in session.execute(
                text("SELECT id FROM aqp_experiments WHERE project_id = :id"),
                {"id": identifier},
            ).mappings():
                edges.append(
                    OwnershipEdge(
                        from_id=str(row["id"]),
                        from_kind="Experiment",
                        to_id=identifier,
                        to_kind="Project",
                        relation="IN_PROJECT",
                    )
                )
            for row in session.execute(
                text("SELECT id FROM aqp_resources WHERE project_id = :id"),
                {"id": identifier},
            ).mappings():
                edges.append(
                    OwnershipEdge(
                        from_id=str(row["id"]),
                        from_kind="Resource",
                        to_id=identifier,
                        to_kind="Project",
                        relation="IN_PROJECT",
                    )
                )
        elif kind == "Experiment":
            for row in session.execute(
                text("SELECT id FROM aqp_tests WHERE experiment_id = :id"),
                {"id": identifier},
            ).mappings():
                edges.append(
                    OwnershipEdge(
                        from_id=identifier,
                        from_kind="Experiment",
                        to_id=str(row["id"]),
                        to_kind="Test",
                        relation="IN_EXPERIMENT",
                    )
                )
            for row in session.execute(
                text(
                    "SELECT id FROM aqp_experiments WHERE parent_experiment_id = :id"
                ),
                {"id": identifier},
            ).mappings():
                edges.append(
                    OwnershipEdge(
                        from_id=identifier,
                        from_kind="Experiment",
                        to_id=str(row["id"]),
                        to_kind="Experiment",
                        relation="PARENT_OF",
                    )
                )
        elif kind == "Resource":
            for row in session.execute(
                text(
                    "SELECT to_id, relation FROM aqp_resource_relations "
                    "WHERE from_id = :id"
                ),
                {"id": identifier},
            ).mappings():
                rel = str(row["relation"]).upper()
                edges.append(
                    OwnershipEdge(
                        from_id=identifier,
                        from_kind="Resource",
                        to_id=str(row["to_id"]),
                        to_kind="Resource",
                        relation=rel,
                    )
                )
        return edges


__all__ = ["PostgresOwnershipGraphStore"]
