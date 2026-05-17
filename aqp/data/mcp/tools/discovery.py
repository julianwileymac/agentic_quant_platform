"""DataMCP tools backing the active discovery surface (phase 1).

Exposes ``data.discovery.browse``, ``data.discovery.describe``, and
``data.discovery.promote`` so agents can inventory uningested
external sources without bypassing the
:class:`DataMCPTool` boundary (AGENTS rule 22).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.discovery import DiscoveryService
from aqp.data.discovery.types import PromoteRequest
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

_service = DiscoveryService()


class BrowseDiscoveryInput(BaseModel):
    lifecycle: str | None = Field(
        default=None,
        description="Filter by lifecycle: ingested | pending | orphan | external_only.",
    )
    provider: str | None = Field(default=None)
    kind: str | None = Field(
        default=None,
        description="Filter by dataset kind (iceberg / api / external / ...).",
    )
    search: str | None = Field(default=None, description="Substring match on name / provider / description.")
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class BrowseDiscoveryTool(DataMCPTool):
    name = "data.discovery.browse"
    description = (
        "Browse the unified discovery surface — ingested datasets, pending external sources, "
        "Iceberg orphans, and Airbyte connection inventory in one stream. Use this before "
        "deciding whether to promote a source via the Airbyte builder."
    )
    args_schema = BrowseDiscoveryInput
    category = "discovery"
    tags = ("discovery", "catalog", "browse")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        lifecycle: str | None = None,
        provider: str | None = None,
        kind: str | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        page = _service.list(
            lifecycle=lifecycle,  # type: ignore[arg-type]
            provider=provider,
            kind=kind,
            search=search,
            limit=int(limit),
        )
        # Tenancy filter: drop entries whose Postgres row belongs to a
        # different workspace. Virtual entries (orphan: / library: /
        # airbyte:) never carry a workspace and are always shown so the
        # operator can still see uningested external sources.
        ws = ctx.workspace_id
        items: list[Any] = []
        for entry in page.items:
            entry_ws = (entry.workspace_id or "") if hasattr(entry, "workspace_id") else ""
            is_virtual = entry.id and entry.id.startswith(
                ("orphan:", "library:", "airbyte:")
            )
            if ws and entry_ws and entry_ws != ws and not is_virtual:
                # Cross-tenant data — skip it.
                continue
            items.append(entry.model_dump(mode="json"))
        return MCPToolResult(
            ok=True,
            data={
                "items": items,
                "by_lifecycle": page.by_lifecycle,
                "total": page.total,
                "next_cursor": page.next_cursor,
            },
            rows_returned=len(items),
            summary=f"discovery browse returned {len(items)} entries",
        )


class DescribeDiscoveryInput(BaseModel):
    entry_id: str = Field(..., description="Discovery entry id (DatasetCatalog id or virtual sentinel)")


@register_data_mcp_tool
class DescribeDiscoveryTool(DataMCPTool):
    name = "data.discovery.describe"
    description = (
        "Return the full DiscoveryEntry payload (description, tags, suggested connector, "
        "external spec) for a single id."
    )
    args_schema = DescribeDiscoveryInput
    category = "discovery"
    tags = ("discovery", "describe")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, entry_id: str) -> MCPToolResult:
        entry = _service.get(entry_id)
        if entry is None:
            return MCPToolResult(
                ok=False,
                error=f"discovery entry {entry_id!r} not found",
                summary="describe miss",
            )
        return MCPToolResult(
            ok=True,
            data=entry.model_dump(mode="json"),
            summary=f"described {entry_id}",
        )


class PromoteDiscoveryInput(BaseModel):
    entry_id: str = Field(..., description="Discovery entry id to promote")
    target_kind: str = Field(
        default="airbyte_builder",
        description="Promotion target: airbyte_builder | fetcher_stub.",
    )
    notes: str | None = Field(default=None)


@register_data_mcp_tool
class PromoteDiscoveryTool(DataMCPTool):
    name = "data.discovery.promote"
    description = (
        "Promote an uningested discovery entry into an ingestion path. "
        "Returns the deep-link URL the operator opens in the Airbyte builder."
    )
    args_schema = PromoteDiscoveryInput
    category = "discovery"
    tags = ("discovery", "promote")
    mutates = True
    required_scopes = ("data:write",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        entry_id: str,
        target_kind: str = "airbyte_builder",
        notes: str | None = None,
    ) -> MCPToolResult:
        try:
            result = _service.promote(
                entry_id,
                target_kind=target_kind,
                notes=notes,
                actor=ctx.actor,
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
            )
        except LookupError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="promote miss")
        return MCPToolResult(
            ok=True,
            data=result,
            summary=f"promoted {entry_id} -> {target_kind}",
            metadata={"redirect_url": result["redirect_url"]},
        )


__all__ = ["BrowseDiscoveryTool", "DescribeDiscoveryTool", "PromoteDiscoveryTool"]
