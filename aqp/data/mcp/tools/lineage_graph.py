"""DataMCP tools for the bipartite lineage graph (Workstream A).

Exposes read-only queries against the
``lineage_dataset_vertex`` / ``lineage_transform_vertex`` /
``lineage_edge`` tables:

- ``data.lineage.ancestry`` — recursive upstream walk: "what produced
  this dataset, and what produced that, and so on".
- ``data.lineage.impact`` — recursive downstream walk: "if this
  dataset version changes, what depends on it".

Both tools return a flat list of vertices + edges so the agent (or the
frontend graph viewer) can render the slice without follow-up calls.
The walks are bounded by ``max_depth`` (default 8, max 32) to keep the
worst case tractable.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


# ---------------------------------------------------------------------------
# Shared shape
# ---------------------------------------------------------------------------


def _vertex_dict(row: Any, *, kind: str) -> dict[str, Any]:
    """Serialise a DatasetVertex or TransformVertex into the agent-friendly shape."""
    if kind == "dataset":
        return {
            "id": row.id,
            "kind": "dataset",
            "namespace": row.namespace,
            "name": row.name,
            "content_hash": row.content_hash,
            "iceberg_snapshot_id": row.iceberg_snapshot_id,
            "manifest_list_location": row.manifest_list_location,
            "medallion_layer": row.medallion_layer,
            "row_count": row.row_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    return {
        "id": row.id,
        "kind": "transform",
        "job_name": row.job_name,
        "run_id": row.run_id,
        "code_version": row.code_version,
        "transform_kind": row.transform_kind,
        "actor": row.actor,
        "actor_kind": row.actor_kind,
        "service_name": row.service_name,
        "mcp_tool_name": row.mcp_tool_name,
        "signature_present": bool(row.signature),
        "signing_key_id": row.signing_key_id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _edge_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "from_vertex": row.from_vertex,
        "to_vertex": row.to_vertex,
        "edge_type": row.edge_type,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _walk(
    *,
    session: Any,
    start_ids: list[str],
    direction: str,
    max_depth: int,
    edge_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Iterative BFS across :class:`LineageEdge` rows.

    ``direction='upstream'`` follows edges INTO the seed vertices
    (``edge.to_vertex IN seen``); ``direction='downstream'`` follows
    edges OUT of seen vertices (``edge.from_vertex IN seen``).
    """
    from aqp.persistence.models_lineage_graph import (
        DatasetVertex,
        LineageEdge,
        TransformVertex,
    )

    seen_vertices: dict[str, dict[str, Any]] = {}
    seen_edges: dict[str, dict[str, Any]] = {}
    frontier: set[str] = set(start_ids)

    for depth in range(max_depth):
        if not frontier:
            break
        if direction == "upstream":
            edge_rows = (
                session.query(LineageEdge)
                .filter(LineageEdge.to_vertex.in_(list(frontier)))
                .limit(edge_limit)
                .all()
            )
            next_frontier = {row.from_vertex for row in edge_rows}
        else:
            edge_rows = (
                session.query(LineageEdge)
                .filter(LineageEdge.from_vertex.in_(list(frontier)))
                .limit(edge_limit)
                .all()
            )
            next_frontier = {row.to_vertex for row in edge_rows}

        for edge in edge_rows:
            seen_edges[edge.id] = _edge_dict(edge)

        if not next_frontier:
            break

        # Hydrate vertices in the next frontier so the caller has the
        # full slice. We try DatasetVertex first then TransformVertex.
        to_fetch = next_frontier - set(seen_vertices)
        if not to_fetch:
            frontier = next_frontier
            continue

        ds_rows = (
            session.query(DatasetVertex)
            .filter(DatasetVertex.id.in_(list(to_fetch)))
            .all()
        )
        for row in ds_rows:
            seen_vertices[row.id] = _vertex_dict(row, kind="dataset")

        tx_rows = (
            session.query(TransformVertex)
            .filter(TransformVertex.id.in_(list(to_fetch)))
            .all()
        )
        for row in tx_rows:
            seen_vertices[row.id] = _vertex_dict(row, kind="transform")

        frontier = next_frontier

    return list(seen_vertices.values()), list(seen_edges.values())


# ---------------------------------------------------------------------------
# Ancestry
# ---------------------------------------------------------------------------


class LineageAncestryInput(BaseModel):
    namespace: str = Field(description="Dataset namespace (e.g. 'aqp_silver_equities_bars').")
    name: str = Field(description="Dataset name within the namespace.")
    content_hash: str | None = Field(
        default=None,
        description=(
            "Optional snapshot content hash to pin the ancestry walk to "
            "a specific version. When omitted the latest snapshot wins."
        ),
    )
    max_depth: int = Field(default=8, ge=1, le=32)
    edge_limit: int = Field(default=1000, ge=1, le=10000)


@register_data_mcp_tool
class LineageAncestryTool(DataMCPTool):
    """Walk upstream from a dataset snapshot to its source vertices."""

    name = "data.lineage.ancestry"
    description = (
        "Walk upstream from a dataset snapshot through the bipartite "
        "lineage graph. Returns every vertex (dataset / transform) and "
        "edge encountered up to ``max_depth`` hops. Use this to answer "
        "'what produced this version of dataset X?'."
    )
    args_schema = LineageAncestryInput
    category = "lineage"
    tags = ("lineage", "graph", "ancestry")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        namespace: str,
        name: str,
        content_hash: str | None = None,
        max_depth: int = 8,
        edge_limit: int = 1000,
    ) -> MCPToolResult:
        from sqlalchemy import desc

        from aqp.persistence.db import get_session
        from aqp.persistence.models_lineage_graph import DatasetVertex

        with get_session() as session:
            query = session.query(DatasetVertex).filter(
                DatasetVertex.namespace == namespace,
                DatasetVertex.name == name,
            )
            if content_hash:
                query = query.filter(DatasetVertex.content_hash == content_hash)
            else:
                query = query.order_by(desc(DatasetVertex.created_at))
            root = query.first()
            if root is None:
                return MCPToolResult(
                    ok=False,
                    error=f"no DatasetVertex for {namespace}.{name}",
                )
            vertices = [_vertex_dict(root, kind="dataset")]
            upstream_vertices, edges = _walk(
                session=session,
                start_ids=[root.id],
                direction="upstream",
                max_depth=max_depth,
                edge_limit=edge_limit,
            )
            vertices.extend(upstream_vertices)
            return MCPToolResult(
                ok=True,
                data={
                    "root": vertices[0],
                    "vertices": vertices,
                    "edges": edges,
                    "depth_limit": max_depth,
                },
                summary=(
                    f"ancestry of {namespace}.{name}: "
                    f"{len(vertices)} vertices, {len(edges)} edges"
                ),
            )


# ---------------------------------------------------------------------------
# Impact
# ---------------------------------------------------------------------------


class LineageImpactInput(BaseModel):
    namespace: str
    name: str
    content_hash: str | None = None
    max_depth: int = Field(default=8, ge=1, le=32)
    edge_limit: int = Field(default=1000, ge=1, le=10000)


@register_data_mcp_tool
class LineageImpactTool(DataMCPTool):
    """Walk downstream from a dataset snapshot to its dependents."""

    name = "data.lineage.impact"
    description = (
        "Walk downstream from a dataset snapshot through the bipartite "
        "lineage graph. Returns every vertex (dataset / transform) and "
        "edge encountered up to ``max_depth`` hops. Use this to answer "
        "'if I change this version of dataset X, what breaks?'."
    )
    args_schema = LineageImpactInput
    category = "lineage"
    tags = ("lineage", "graph", "impact")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        namespace: str,
        name: str,
        content_hash: str | None = None,
        max_depth: int = 8,
        edge_limit: int = 1000,
    ) -> MCPToolResult:
        from sqlalchemy import desc

        from aqp.persistence.db import get_session
        from aqp.persistence.models_lineage_graph import DatasetVertex

        with get_session() as session:
            query = session.query(DatasetVertex).filter(
                DatasetVertex.namespace == namespace,
                DatasetVertex.name == name,
            )
            if content_hash:
                query = query.filter(DatasetVertex.content_hash == content_hash)
            else:
                query = query.order_by(desc(DatasetVertex.created_at))
            root = query.first()
            if root is None:
                return MCPToolResult(
                    ok=False,
                    error=f"no DatasetVertex for {namespace}.{name}",
                )
            vertices = [_vertex_dict(root, kind="dataset")]
            downstream_vertices, edges = _walk(
                session=session,
                start_ids=[root.id],
                direction="downstream",
                max_depth=max_depth,
                edge_limit=edge_limit,
            )
            vertices.extend(downstream_vertices)
            return MCPToolResult(
                ok=True,
                data={
                    "root": vertices[0],
                    "vertices": vertices,
                    "edges": edges,
                    "depth_limit": max_depth,
                },
                summary=(
                    f"impact of {namespace}.{name}: "
                    f"{len(vertices)} vertices, {len(edges)} edges"
                ),
            )


__all__ = [
    "LineageAncestryTool",
    "LineageImpactTool",
]
