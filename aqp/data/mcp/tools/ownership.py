"""``data.ownership.*`` MCP tools — graph-aware ownership queries.

These tools delegate to :class:`aqp.graph.OwnershipGraphStore` so
agents can answer "what resources can I see?" / "who can read this?"
without hand-rolling joins over the tenancy tables. Compliance with
AGENTS.md hard rule 33.

Three tools today; the Phase 6 frontend wires them into the new
ContextBar's "Members" + "Resources" panels.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.graph import get_ownership_store


# ---------------------------------------------------------------------------
# data.ownership.tree
# ---------------------------------------------------------------------------


class OwnershipTreeInput(BaseModel):
    start_kind: str = Field(
        ...,
        description=(
            "Starting node kind (Organization, Team, User, Workspace, "
            "Project, Lab, Experiment, Test, Resource)."
        ),
    )
    start_id: str = Field(..., description="Starting node id (UUID).")
    edge_kinds: list[str] | None = Field(
        default=None,
        description=(
            "Optional whitelist of edge relations to follow (HAS_TEAM, "
            "HAS_WORKSPACE, OWNS, MEMBER_OF, IN_PROJECT, IN_LAB, ...). "
            "Omit to follow every edge."
        ),
    )
    depth: int = Field(default=2, ge=1, le=6)
    limit: int = Field(default=200, ge=1, le=1000)


@register_data_mcp_tool
class OwnershipTreeTool(DataMCPTool):
    name = "data.ownership.tree"
    description = (
        "Walk the ownership graph outward from a node, returning "
        "{nodes, edges} for the matching subgraph. Use this when an "
        "agent needs to enumerate every resource a workspace owns, "
        "every member of an org, etc."
    )
    args_schema = OwnershipTreeInput
    category = "ownership"
    tags = ("ownership", "graph", "traverse")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        start_kind: str,
        start_id: str,
        edge_kinds: list[str] | None = None,
        depth: int = 2,
        limit: int = 200,
    ) -> MCPToolResult:
        store = get_ownership_store()
        result = store.traverse(
            start_kind=start_kind,
            start_id=start_id,
            edge_kinds=edge_kinds,
            depth=int(depth),
            limit=int(limit),
        )
        return MCPToolResult(
            ok=True,
            data=result,
            rows_returned=len(result.get("nodes", [])),
            summary=(
                f"ownership tree from {start_kind}:{start_id} "
                f"({len(result.get('nodes', []))} nodes / "
                f"{len(result.get('edges', []))} edges)"
            ),
            metadata={"store": store.name},
        )


# ---------------------------------------------------------------------------
# data.ownership.list_resources
# ---------------------------------------------------------------------------


class ListResourcesVisibleInput(BaseModel):
    user_id: str | None = Field(
        default=None,
        description=(
            "User to compute visibility for. Defaults to the calling actor "
            "(ctx.actor) when omitted."
        ),
    )
    resource_type: str | None = Field(
        default=None,
        description=(
            "Optional filter on resource_type (strategy_template, "
            "dataset_template, model_artifact, config, notebook, ...)."
        ),
    )
    limit: int = Field(default=200, ge=1, le=1000)


@register_data_mcp_tool
class ListResourcesVisibleTool(DataMCPTool):
    name = "data.ownership.list_resources"
    description = (
        "Return every Resource a user can see, reachable via the "
        "membership graph (user -> team/workspace/project/org -> owns -> resource). "
        "Optional resource_type filter."
    )
    args_schema = ListResourcesVisibleInput
    category = "ownership"
    tags = ("ownership", "resources", "visibility")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        user_id: str | None = None,
        resource_type: str | None = None,
        limit: int = 200,
    ) -> MCPToolResult:
        target_user = user_id or ctx.actor
        if not target_user:
            return MCPToolResult(
                ok=False,
                error="user_id (or ctx.actor) is required",
                summary="missing user_id",
            )
        store = get_ownership_store()
        nodes = store.list_resources_visible_to(
            user_id=target_user,
            resource_type=resource_type,
            limit=int(limit),
        )
        data = [
            {"id": n.id, "kind": n.kind, "properties": n.properties}
            for n in nodes
        ]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"{len(data)} resources visible to {target_user}",
            metadata={"store": store.name},
        )


# ---------------------------------------------------------------------------
# data.ownership.who_can_read
# ---------------------------------------------------------------------------


class WhoCanReadInput(BaseModel):
    resource_id: str = Field(..., description="Resource UUID to inspect.")


@register_data_mcp_tool
class WhoCanReadTool(DataMCPTool):
    name = "data.ownership.who_can_read"
    description = (
        "List the (user_id, role, scope_kind, scope_id) tuples that "
        "have read access to a Resource via the membership graph. "
        "Inverse of data.ownership.list_resources."
    )
    args_schema = WhoCanReadInput
    category = "ownership"
    tags = ("ownership", "audit", "permissions")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        resource_id: str,
    ) -> MCPToolResult:
        store = get_ownership_store()
        rows = store.who_can_read(resource_id=resource_id)
        return MCPToolResult(
            ok=True,
            data=rows,
            rows_returned=len(rows),
            summary=f"{len(rows)} principals can read {resource_id}",
            metadata={"store": store.name},
        )


__all__ = [
    "ListResourcesVisibleTool",
    "OwnershipTreeTool",
    "WhoCanReadTool",
]
