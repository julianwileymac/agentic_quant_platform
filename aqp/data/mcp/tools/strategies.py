"""``data.strategies.templates.*`` MCP tools — Phase 7 LEAN catalog.

Read-only browsing + clone-to-workspace over the templates registered
in the polymorphic ``resources`` table by
``scripts.ingest_lean_templates``.

Tools:

- ``data.strategies.templates.search`` — list / search by tag / asset class.
- ``data.strategies.templates.describe`` — full payload incl. source code.
- ``data.strategies.templates.clone_to_workspace`` — fork into a user-
  owned Resource, optionally with the AST translator applied.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower().strip()).strip("-")
    return base[:180] or "template"


def _resource_summary(row: Any) -> dict[str, Any]:
    meta = dict(row.meta or {})
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "uri": row.uri,
        "tags": list(row.tags or []),
        "asset_classes": meta.get("asset_classes") or [],
        "indicators": meta.get("indicators") or [],
        "framework": meta.get("framework") or "lean",
        "class_name": meta.get("class_name"),
        "source_path": meta.get("source_path"),
    }


# ---------------------------------------------------------------------------
# data.strategies.templates.search
# ---------------------------------------------------------------------------


class SearchTemplatesInput(BaseModel):
    query: str | None = Field(
        default=None,
        description="Substring matched against name + description + class_name.",
    )
    asset_class: str | None = Field(
        default=None,
        description="Filter by asset class (equities/options/futures/crypto/forex).",
    )
    tag: str | None = Field(
        default=None,
        description="Filter by a single tag (machine_learning/multi_leg/momentum/...).",
    )
    framework: str | None = Field(
        default=None, description="Filter by framework (default: 'lean')."
    )
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class SearchTemplatesTool(DataMCPTool):
    name = "data.strategies.templates.search"
    description = (
        "Search the strategy-template catalog ingested from "
        "QuantConnect LEAN (and any community / internal templates). "
        "Returns summaries — call data.strategies.templates.describe "
        "for the full source code."
    )
    args_schema = SearchTemplatesInput
    category = "strategies"
    tags = ("strategies", "templates", "lean", "search")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        query: str | None = None,
        asset_class: str | None = None,
        tag: str | None = None,
        framework: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_resources import Resource

        with get_session() as session:
            stmt = (
                select(Resource)
                .where(Resource.resource_type == "strategy_template")
                .order_by(Resource.name)
                .limit(limit)
            )
            if query:
                like = f"%{query.lower()}%"
                stmt = stmt.where(
                    (Resource.name.ilike(like))
                    | (Resource.description.ilike(like))
                )
            rows = session.execute(stmt).scalars().all()
        # In-memory filters on jsonb fields keep the SQL simple.
        out: list[dict[str, Any]] = []
        for row in rows:
            summary = _resource_summary(row)
            if asset_class and asset_class not in (summary["asset_classes"] or []):
                continue
            if tag and tag not in (summary["tags"] or []):
                continue
            if framework and summary["framework"] != framework:
                continue
            out.append(summary)
        return MCPToolResult(
            ok=True,
            data=out,
            rows_returned=len(out),
            summary=f"{len(out)} strategy templates",
        )


# ---------------------------------------------------------------------------
# data.strategies.templates.describe
# ---------------------------------------------------------------------------


class DescribeTemplateInput(BaseModel):
    template_id: str = Field(..., description="Resource UUID or slug.")


@register_data_mcp_tool
class DescribeTemplateTool(DataMCPTool):
    name = "data.strategies.templates.describe"
    description = (
        "Return the full strategy-template payload including the raw "
        "LEAN source code. Use this before clone_to_workspace so the "
        "agent can preview the template."
    )
    args_schema = DescribeTemplateInput
    category = "strategies"
    tags = ("strategies", "templates", "describe")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        template_id: str,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_resources import Resource

        with get_session() as session:
            row = session.get(Resource, template_id)
            if row is None:
                row = (
                    session.query(Resource)
                    .filter(
                        Resource.resource_type == "strategy_template",
                        Resource.slug == template_id,
                    )
                    .one_or_none()
                )
            if row is None or row.resource_type != "strategy_template":
                return MCPToolResult(
                    ok=False,
                    error=f"strategy template {template_id!r} not found",
                    summary="describe miss",
                )
            data = _resource_summary(row)
            data["raw_source"] = (row.meta or {}).get("raw_source")
        return MCPToolResult(ok=True, data=data, summary=f"described {data['slug']}")


# ---------------------------------------------------------------------------
# data.strategies.templates.clone_to_workspace
# ---------------------------------------------------------------------------


class CloneTemplateInput(BaseModel):
    template_id: str = Field(..., description="Source template id or slug.")
    new_slug: str | None = Field(
        default=None,
        description="Override the slug for the cloned resource (auto-generated if omitted).",
    )
    translate: bool = Field(
        default=True,
        description="When true, run the LEAN AST translator before storing the clone.",
    )


@register_data_mcp_tool
class CloneTemplateToWorkspaceTool(DataMCPTool):
    name = "data.strategies.templates.clone_to_workspace"
    description = (
        "Fork a strategy template into the current user's workspace. "
        "When translate=true the LEAN source is rewritten into a "
        "FrameworkAlgorithm skeleton ready to run on AQP's engines."
    )
    args_schema = CloneTemplateInput
    category = "strategies"
    tags = ("strategies", "templates", "clone", "translate")
    mutates = True
    required_scopes = ("data:write",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        template_id: str,
        new_slug: str | None = None,
        translate: bool = True,
    ) -> MCPToolResult:
        if not ctx.actor:
            return MCPToolResult(
                ok=False,
                error="ctx.actor is required to clone a template",
                summary="missing actor",
            )

        from datetime import datetime

        from aqp.persistence.db import get_session
        from aqp.persistence.models_resources import Resource, ResourceRelation

        with get_session() as session:
            source_row = session.get(Resource, template_id)
            if source_row is None:
                source_row = (
                    session.query(Resource)
                    .filter(
                        Resource.resource_type == "strategy_template",
                        Resource.slug == template_id,
                    )
                    .one_or_none()
                )
            if source_row is None or source_row.resource_type != "strategy_template":
                return MCPToolResult(
                    ok=False,
                    error=f"strategy template {template_id!r} not found",
                    summary="clone miss",
                )
            source_meta = dict(source_row.meta or {})
            raw_source = source_meta.get("raw_source", "")
            payload = raw_source
            translated = False
            if translate and raw_source:
                from aqp.strategies.lean.translator import translate_lean_to_framework

                payload = translate_lean_to_framework(
                    raw_source, class_name=source_meta.get("class_name")
                )
                translated = True

            slug = new_slug or _slugify(f"{source_row.slug}-clone")
            cloned = Resource(
                name=f"{source_row.name} (cloned)",
                slug=slug,
                resource_type="strategy_template",
                uri=f"workspace://{ctx.workspace_id or 'default'}/{slug}",
                description=source_row.description,
                owner_scope_kind="user",
                owner_scope_id=str(ctx.actor),
                meta={
                    **source_meta,
                    "raw_source": payload,
                    "translated_from_lean": translated,
                    "cloned_from": source_row.id,
                },
                tags=list(source_row.tags or []),
                visibility="private",
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(cloned)
            session.flush()

            session.add(
                ResourceRelation(
                    from_id=cloned.id,
                    to_id=source_row.id,
                    relation="translated_from" if translated else "clones",
                    details={"translated": translated},
                    created_at=datetime.utcnow(),
                )
            )
            session.commit()
            cloned_id = cloned.id
            cloned_slug = cloned.slug

        return MCPToolResult(
            ok=True,
            data={
                "id": cloned_id,
                "slug": cloned_slug,
                "translated": translated,
                "source_id": source_row.id if source_row else None,
            },
            summary=f"cloned {template_id} -> {cloned_slug} (translated={translated})",
            metadata={
                "redirect_url": f"/resources/{cloned_id}",
            },
        )


__all__ = [
    "CloneTemplateToWorkspaceTool",
    "DescribeTemplateTool",
    "SearchTemplatesTool",
]
