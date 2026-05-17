"""``data.tests.*`` MCP tools — assertion browsing for agents.

Read-only browsing over the Phase 1 ``tests`` table.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session
from aqp.persistence.models_experiments import Test


def _row_to_dict(row: Test) -> dict[str, Any]:
    return {
        "id": row.id,
        "experiment_id": row.experiment_id,
        "slug": row.slug,
        "name": row.name,
        "assertion_kind": row.assertion_kind,
        "passed": row.passed,
        "details": dict(row.details or {}),
        "run_ref_table": row.run_ref_table,
        "run_ref_id": row.run_ref_id,
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "owner_user_id": row.owner_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ---------------------------------------------------------------------------
# data.tests.list
# ---------------------------------------------------------------------------


class ListTestsInput(BaseModel):
    experiment_id: str | None = Field(
        default=None, description="Filter to one experiment's tests."
    )
    passed: bool | None = Field(
        default=None, description="Filter on the verdict (True / False)."
    )
    assertion_kind: str | None = Field(default=None)
    limit: int = Field(default=100, ge=1, le=500)


@register_data_mcp_tool
class ListTestsTool(DataMCPTool):
    name = "data.tests.list"
    description = (
        "List tests (assertions) in the active workspace/project, "
        "optionally filtered by experiment / verdict / kind."
    )
    args_schema = ListTestsInput
    category = "tests"
    tags = ("tests", "assertions", "list")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        experiment_id: str | None = None,
        passed: bool | None = None,
        assertion_kind: str | None = None,
        limit: int = 100,
    ) -> MCPToolResult:
        with get_session() as session:
            query = select(Test).order_by(Test.updated_at.desc()).limit(limit)
            if experiment_id:
                query = query.where(Test.experiment_id == experiment_id)
            elif ctx.project_id:
                query = query.where(Test.project_id == ctx.project_id)
            if passed is not None:
                query = query.where(Test.passed.is_(passed))
            if assertion_kind:
                query = query.where(Test.assertion_kind == assertion_kind)
            rows = session.execute(query).scalars().all()
            data = [_row_to_dict(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"{len(data)} tests",
        )


# ---------------------------------------------------------------------------
# data.tests.describe
# ---------------------------------------------------------------------------


class DescribeTestInput(BaseModel):
    test_id: str = Field(...)


@register_data_mcp_tool
class DescribeTestTool(DataMCPTool):
    name = "data.tests.describe"
    description = "Return the full Test row including evaluation details."
    args_schema = DescribeTestInput
    category = "tests"
    tags = ("tests", "describe")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        test_id: str,
    ) -> MCPToolResult:
        with get_session() as session:
            row = session.get(Test, test_id)
            if row is None:
                return MCPToolResult(
                    ok=False,
                    error=f"test {test_id!r} not found",
                    summary="describe miss",
                )
            return MCPToolResult(
                ok=True,
                data=_row_to_dict(row),
                summary=f"described test {test_id}",
            )


__all__ = ["DescribeTestTool", "ListTestsTool"]
