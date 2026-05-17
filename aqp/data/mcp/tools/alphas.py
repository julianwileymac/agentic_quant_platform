"""``data.alphas.*`` MCP tools — alpha factor catalog.

Read-only browsing over the polymorphic ``resources`` table filtered
to ``resource_type='alpha_factor'`` so the
:class:`aqp.agents.quant.AlphaResearcher` can retrieve prior factor
proposals (with their compiled status + measured performance) from
the canonical catalog without bypassing the DataMCP boundary.

The matching ``AlphaFactor`` resource shape is Phase 8 — until then
the tools degrade gracefully and return empty result sets when the
backing table is missing the discriminator.

Tools provided:

- ``data.alphas.search`` — list / filter alpha factor resources.
- ``data.alphas.describe`` — describe one alpha factor including
  the symbolic formula + last measured Sharpe / IR / max-drawdown.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session


_ALPHA_RESOURCE_TYPE = "alpha_factor"


def _resource_to_dict(row: Any) -> dict[str, Any]:
    meta = dict(getattr(row, "meta", {}) or {})
    return {
        "id": getattr(row, "id", None),
        "name": getattr(row, "name", None),
        "slug": getattr(row, "slug", None),
        "resource_type": getattr(row, "resource_type", None),
        "owner_scope_kind": getattr(row, "owner_scope_kind", None),
        "owner_scope_id": getattr(row, "owner_scope_id", None),
        "visibility": getattr(row, "visibility", None),
        "tags": list(getattr(row, "tags", []) or []),
        "meta": meta,
        "formula": meta.get("formula"),
        "rationale": meta.get("rationale"),
        "metrics": meta.get("metrics") or {},
        "created_at": _isoformat(getattr(row, "created_at", None)),
        "updated_at": _isoformat(getattr(row, "updated_at", None)),
    }


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# data.alphas.search
# ---------------------------------------------------------------------------


class SearchAlphasInput(BaseModel):
    query: str | None = Field(
        default=None, description="Substring match on name / slug / rationale (case-insensitive)."
    )
    min_sharpe: float | None = Field(
        default=None,
        description="Minimum measured Sharpe ratio (filters by meta.metrics.sharpe).",
    )
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class SearchAlphasTool(DataMCPTool):
    name = "data.alphas.search"
    description = (
        "Search the alpha factor catalog (resources of type 'alpha_factor'). "
        "Use to retrieve prior wins / losses before proposing a new factor "
        "to avoid re-trying known dead-ends."
    )
    args_schema = SearchAlphasInput
    category = "alphas"
    tags = ("alphas", "factors", "search")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        query: str | None = None,
        min_sharpe: float | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        try:
            from aqp.persistence.models_resources import Resource
        except Exception:
            return MCPToolResult(ok=True, data={"items": []}, rows_returned=0, summary="resources unavailable")
        with get_session() as session:
            stmt = select(Resource).where(Resource.resource_type == _ALPHA_RESOURCE_TYPE)
            if query:
                like = f"%{query.lower()}%"
                stmt = stmt.where(
                    (Resource.name.ilike(like)) | (Resource.slug.ilike(like))
                )
            stmt = stmt.order_by(Resource.updated_at.desc()).limit(int(limit) * 2)
            rows = list(session.execute(stmt).scalars())
        items = [_resource_to_dict(r) for r in rows]
        if min_sharpe is not None:
            items = [
                it
                for it in items
                if float((it.get("metrics") or {}).get("sharpe", 0.0) or 0.0) >= float(min_sharpe)
            ]
        items = items[: int(limit)]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"{len(items)} alpha factors",
        )


# ---------------------------------------------------------------------------
# data.alphas.describe
# ---------------------------------------------------------------------------


class DescribeAlphaInput(BaseModel):
    alpha_id: str | None = Field(default=None, description="Resource id (PK of resources).")
    slug: str | None = Field(default=None, description="Alpha slug (alternative to id).")


@register_data_mcp_tool
class DescribeAlphaTool(DataMCPTool):
    name = "data.alphas.describe"
    description = (
        "Describe one alpha factor in detail (symbolic formula + rationale + "
        "measured Sharpe / IR / max-drawdown)."
    )
    args_schema = DescribeAlphaInput
    category = "alphas"
    tags = ("alphas", "factors", "describe")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        alpha_id: str | None = None,
        slug: str | None = None,
    ) -> MCPToolResult:
        if not alpha_id and not slug:
            return MCPToolResult(ok=False, error="provide alpha_id or slug")
        try:
            from aqp.persistence.models_resources import Resource
        except Exception:
            return MCPToolResult(ok=False, error="resources model unavailable")
        with get_session() as session:
            if alpha_id:
                row = session.get(Resource, alpha_id)
                if row is not None and row.resource_type != _ALPHA_RESOURCE_TYPE:
                    return MCPToolResult(
                        ok=False, error=f"resource {alpha_id!r} is not an alpha_factor"
                    )
            else:
                stmt = (
                    select(Resource)
                    .where(Resource.resource_type == _ALPHA_RESOURCE_TYPE)
                    .where(Resource.slug == slug)
                    .limit(1)
                )
                row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return MCPToolResult(ok=False, error="alpha factor not found")
            return MCPToolResult(
                ok=True,
                data=_resource_to_dict(row),
                summary=f"alpha {row.slug or row.id}",
            )


__all__ = [
    "DescribeAlphaTool",
    "SearchAlphasTool",
]
