"""``data.brokers.*`` MCP tools — broker positions + account summary.

Read-only browsing over the canonical ``accounts`` / ``account_balances``
/ ``account_positions`` tables so :class:`aqp.agents.quant.StrategyExecutor`
(and any other AgentSpec) can check live state before submitting paper
or live actions — without bypassing the DataMCP boundary or importing
ORM models directly.

Tools provided:

- ``data.brokers.account_summary`` — account-level snapshot (cash /
  equity / margin_used / kill_switch_engaged).
- ``data.brokers.positions`` — list current positions, optionally
  filtered by account / venue.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _account_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "account_id": getattr(row, "account_id", None),
        "venue": getattr(row, "venue", None),
        "broker": getattr(row, "broker", None),
        "currency": getattr(row, "currency", None),
        "status": getattr(row, "status", None),
        "is_paper": bool(getattr(row, "is_paper", False)),
        "created_at": _isoformat(getattr(row, "created_at", None)),
        "updated_at": _isoformat(getattr(row, "updated_at", None)),
    }


def _balance_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "account_id": getattr(row, "account_id", None),
        "cash": _to_float(getattr(row, "cash", None)),
        "equity": _to_float(getattr(row, "equity", None)),
        "buying_power": _to_float(getattr(row, "buying_power", None)),
        "margin_used": _to_float(getattr(row, "margin_used", None)),
        "as_of": _isoformat(getattr(row, "as_of", None)),
    }


def _position_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "account_id": getattr(row, "account_id", None),
        "vt_symbol": getattr(row, "vt_symbol", None),
        "quantity": _to_float(getattr(row, "quantity", None)),
        "average_price": _to_float(getattr(row, "average_price", None)),
        "market_value": _to_float(getattr(row, "market_value", None)),
        "unrealized_pnl": _to_float(getattr(row, "unrealized_pnl", None)),
        "realized_pnl": _to_float(getattr(row, "realized_pnl", None)),
        "side": getattr(row, "position_side", None) or getattr(row, "side", None),
        "as_of": _isoformat(getattr(row, "as_of", None)),
    }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _kill_switch_status() -> dict[str, Any]:
    try:
        from aqp.risk.kill_switch import status

        return dict(status() or {})
    except Exception:
        return {"engaged": False, "error": "kill_switch_unavailable"}


# ---------------------------------------------------------------------------
# data.brokers.account_summary
# ---------------------------------------------------------------------------


class AccountSummaryInput(BaseModel):
    account_id: str | None = Field(
        default=None,
        description="Broker account id (filters to one account). Omit to summarise all.",
    )
    venue: str | None = Field(
        default=None, description="Broker venue (alpaca / ibkr / tradier / sim)."
    )


@register_data_mcp_tool
class AccountSummaryTool(DataMCPTool):
    name = "data.brokers.account_summary"
    description = (
        "Return the account-level snapshot (cash / equity / margin_used) for the "
        "active workspace, plus the global kill-switch status. Use before any "
        "paper / live action."
    )
    args_schema = AccountSummaryInput
    category = "brokers"
    tags = ("brokers", "accounts", "summary")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        account_id: str | None = None,
        venue: str | None = None,
    ) -> MCPToolResult:
        try:
            from aqp.persistence.models_accounts import (
                AccountBalanceRow,
                AccountRow,
            )
        except Exception:
            return MCPToolResult(
                ok=True,
                data={"accounts": [], "balances": [], "kill_switch": _kill_switch_status()},
                summary="accounts model unavailable",
            )
        try:
            with get_session() as session:
                stmt = select(AccountRow)
                if account_id:
                    stmt = stmt.where(AccountRow.account_id == account_id)
                if venue:
                    stmt = stmt.where(AccountRow.venue == venue)
                accounts = [_account_to_dict(r) for r in session.execute(stmt).scalars()]
                balance_stmt = (
                    select(AccountBalanceRow)
                    .order_by(AccountBalanceRow.as_of.desc())
                    .limit(50)
                )
                if account_id:
                    balance_stmt = (
                        select(AccountBalanceRow)
                        .where(AccountBalanceRow.account_id == account_id)
                        .order_by(AccountBalanceRow.as_of.desc())
                        .limit(20)
                    )
                balances = [_balance_to_dict(r) for r in session.execute(balance_stmt).scalars()]
        except Exception:
            # Accounts tables might not exist on every deployment yet.
            # Degrade gracefully — kill_switch status is still useful.
            accounts, balances = [], []
        return MCPToolResult(
            ok=True,
            data={
                "accounts": accounts,
                "balances": balances,
                "kill_switch": _kill_switch_status(),
            },
            rows_returned=len(accounts),
            summary=f"{len(accounts)} accounts; kill_switch={_kill_switch_status().get('engaged')}",
        )


# ---------------------------------------------------------------------------
# data.brokers.positions
# ---------------------------------------------------------------------------


class PositionsInput(BaseModel):
    account_id: str | None = Field(
        default=None, description="Filter to one account."
    )
    vt_symbol: str | None = Field(
        default=None, description="Filter to one symbol."
    )
    limit: int = Field(default=200, ge=1, le=2000)


@register_data_mcp_tool
class PositionsTool(DataMCPTool):
    name = "data.brokers.positions"
    description = (
        "List current broker positions across the active workspace (or one "
        "account / one symbol when filtered). Reports quantity, average_price, "
        "market_value, unrealized_pnl, realized_pnl."
    )
    args_schema = PositionsInput
    category = "brokers"
    tags = ("brokers", "positions", "list")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        account_id: str | None = None,
        vt_symbol: str | None = None,
        limit: int = 200,
    ) -> MCPToolResult:
        try:
            from aqp.persistence.models_accounts import AccountPositionRow
        except Exception:
            return MCPToolResult(ok=True, data={"items": []}, summary="positions model unavailable")
        try:
            with get_session() as session:
                stmt = select(AccountPositionRow)
                if account_id:
                    stmt = stmt.where(AccountPositionRow.account_id == account_id)
                if vt_symbol:
                    stmt = stmt.where(AccountPositionRow.vt_symbol == vt_symbol)
                stmt = stmt.limit(int(limit))
                items = [_position_to_dict(r) for r in session.execute(stmt).scalars()]
        except Exception:
            items = []
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"{len(items)} positions",
        )


__all__ = [
    "AccountSummaryTool",
    "PositionsTool",
]
