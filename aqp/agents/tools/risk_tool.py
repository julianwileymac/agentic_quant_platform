"""Risk audit + kill switch tools."""
from __future__ import annotations

import json
import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RiskCheckInput(BaseModel):
    backtest_id: str = Field(..., description="The backtest_runs.id to audit.")


class RiskCheckTool(BaseTool):
    name: str = "risk_check"
    description: str = (
        "Audit a completed backtest for risk-limit breaches (position cap, drawdown, daily loss, "
        "concentration). Returns a JSON list of breaches (empty = pass)."
    )
    args_schema: type[BaseModel] = RiskCheckInput

    def _run(self, backtest_id: str) -> str:  # type: ignore[override]
        from aqp.risk.manager import RiskManager

        try:
            report = RiskManager().audit_backtest(backtest_id)
        except Exception as e:
            logger.exception("Risk audit failed")
            return f"ERROR: {e}"
        return json.dumps(report, default=str, indent=2)


class KillSwitchInput(BaseModel):
    reason: str = Field(..., description="Why are we halting? Will be recorded on the ledger.")
    engage: bool = Field(default=True, description="True to engage, False to reset.")


class KillSwitchTool(BaseTool):
    name: str = "kill_switch"
    description: str = (
        "Engage (or release) the platform-wide kill switch. While engaged, no new orders are "
        "routed. The Meta-Agent is the only role authorised to flip this."
    )
    args_schema: type[BaseModel] = KillSwitchInput

    def _run(self, reason: str, engage: bool = True) -> str:  # type: ignore[override]
        from aqp.risk.kill_switch import engage as _engage
        from aqp.risk.kill_switch import release as _release

        try:
            if engage:
                _engage(reason)
                return f"KILL SWITCH ENGAGED — reason: {reason}"
            _release()
            return "KILL SWITCH RELEASED"
        except Exception as e:
            return f"ERROR: {e}"


class LedgerQueryInput(BaseModel):
    backtest_id: str | None = None
    entry_type: str | None = None
    limit: int = 50


class LedgerTool(BaseTool):
    name: str = "ledger"
    description: str = "Read recent entries from the Execution Ledger (signals, orders, fills, risk events)."
    args_schema: type[BaseModel] = LedgerQueryInput

    def _run(  # type: ignore[override]
        self,
        backtest_id: str | None = None,
        entry_type: str | None = None,
        limit: int = 50,
    ) -> str:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models import LedgerEntry

        with get_session() as session:
            stmt = select(LedgerEntry).order_by(LedgerEntry.created_at.desc()).limit(limit)
            if backtest_id:
                stmt = stmt.where(LedgerEntry.backtest_id == backtest_id)
            if entry_type:
                stmt = stmt.where(LedgerEntry.entry_type == entry_type)
            rows = session.execute(stmt).scalars().all()
            out = [
                {
                    "id": r.id,
                    "type": r.entry_type,
                    "level": r.level,
                    "message": r.message,
                    "payload": r.payload,
                    "created_at": str(r.created_at),
                }
                for r in rows
            ]
        return json.dumps(out, default=str, indent=2) if out else "No entries."
