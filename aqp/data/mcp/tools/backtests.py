"""``data.backtests.*`` MCP tools — backtest run inspection.

Read-only browsing over the legacy ``backtest_runs`` table so agents
(particularly :class:`aqp.agents.quant.AlphaResearcher` deciding
whether a candidate factor warrants further exploration) can look up
historical backtest outcomes without bypassing the DataMCP boundary.

Tools provided:

- ``data.backtests.search`` — list backtest runs filtered by
  strategy / experiment_id / status / time window.
- ``data.backtests.describe`` — describe one run including
  performance summary + artifact URIs.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session
from aqp.persistence.models import BacktestRun


def _row_to_dict(row: BacktestRun) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "strategy_id": getattr(row, "strategy_id", None),
        "status": getattr(row, "status", None),
        "engine": getattr(row, "engine", None),
        "start_date": _isoformat(getattr(row, "start_date", None)),
        "end_date": _isoformat(getattr(row, "end_date", None)),
        "initial_cash": getattr(row, "initial_cash", None),
        "final_equity": getattr(row, "final_equity", None),
        "sharpe": getattr(row, "sharpe", None),
        "max_drawdown": getattr(row, "max_drawdown", None),
        "total_return": getattr(row, "total_return", None),
        "summary": dict(getattr(row, "summary", {}) or {}),
        "experiment_id": getattr(row, "experiment_id", None),
        "created_at": _isoformat(getattr(row, "created_at", None)),
        "completed_at": _isoformat(getattr(row, "completed_at", None)),
    }


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# data.backtests.search
# ---------------------------------------------------------------------------


class SearchBacktestsInput(BaseModel):
    strategy_id: str | None = Field(default=None, description="Filter by strategy id.")
    status: str | None = Field(default=None, description="Filter by status.")
    engine: str | None = Field(default=None, description="Filter by engine alias.")
    experiment_id: str | None = Field(
        default=None, description="Filter by umbrella experiment id (rule 34)."
    )
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class SearchBacktestsTool(DataMCPTool):
    name = "data.backtests.search"
    description = (
        "Search recent backtest_runs filtered by strategy / status / engine. "
        "Use before proposing new factor candidates so you can compare "
        "against the historical Sharpe / MDD distribution."
    )
    args_schema = SearchBacktestsInput
    category = "backtests"
    tags = ("backtests", "search")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        strategy_id: str | None = None,
        status: str | None = None,
        engine: str | None = None,
        experiment_id: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        with get_session() as session:
            stmt = select(BacktestRun)
            if strategy_id:
                stmt = stmt.where(BacktestRun.strategy_id == strategy_id)
            if status and hasattr(BacktestRun, "status"):
                stmt = stmt.where(BacktestRun.status == status)
            if engine and hasattr(BacktestRun, "engine"):
                stmt = stmt.where(BacktestRun.engine == engine)
            if experiment_id and hasattr(BacktestRun, "experiment_id"):
                stmt = stmt.where(BacktestRun.experiment_id == experiment_id)
            order_col = getattr(BacktestRun, "created_at", None) or getattr(
                BacktestRun, "completed_at", None
            )
            if order_col is not None:
                stmt = stmt.order_by(order_col.desc())
            stmt = stmt.limit(int(limit))
            # Materialise rows into dicts BEFORE the session closes
            # so SQLAlchemy lazy-load expiry doesn't crash later.
            items = [_row_to_dict(r) for r in session.execute(stmt).scalars()]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"{len(items)} backtest runs",
        )


# ---------------------------------------------------------------------------
# data.backtests.describe
# ---------------------------------------------------------------------------


class DescribeBacktestInput(BaseModel):
    backtest_id: str = Field(description="Backtest run id (PK of backtest_runs).")


@register_data_mcp_tool
class DescribeBacktestTool(DataMCPTool):
    name = "data.backtests.describe"
    description = "Describe one backtest run including summary metrics + artifact pointers."
    args_schema = DescribeBacktestInput
    category = "backtests"
    tags = ("backtests", "describe")

    def run(self, *, ctx: MCPToolContext, backtest_id: str) -> MCPToolResult:
        with get_session() as session:
            row = session.get(BacktestRun, backtest_id)
            if row is None:
                return MCPToolResult(ok=False, error=f"backtest {backtest_id!r} not found")
            payload = _row_to_dict(row)
            return MCPToolResult(
                ok=True,
                data=payload,
                summary=f"backtest {payload.get('id')}",
            )


__all__ = [
    "DescribeBacktestTool",
    "SearchBacktestsTool",
]
