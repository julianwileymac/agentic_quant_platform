"""Portfolio-margin tool — surfaces live capital usage to spec-driven agents.

Returns a snapshot of the current paper / live portfolio:

- Cash, equity, gross / net exposure.
- Per-symbol notional and direction.
- Spare margin headroom (``max_position_pct - current_position_pct``).
- Whether the kill switch is currently engaged.

The Risk Simulator agent uses this before approving any new
``SignalEvent`` so it cannot greenlight an insight that would push the
account into a capital breach.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PortfolioMarginInput(BaseModel):
    session_id: str | None = Field(
        default=None,
        description=(
            "Optional paper-session id to scope the snapshot. When omitted "
            "the most recent paper session is used."
        ),
    )
    include_positions: bool = Field(
        default=True,
        description="Include the per-symbol notional table in the response.",
    )


class PortfolioMarginTool(BaseTool):
    """MCP tool: ``query_portfolio_margin(session_id?, include_positions?)``."""

    name: str = "portfolio_margin"
    description: str = (
        "Snapshot the current portfolio's cash, equity, and per-symbol notional "
        "exposure. Includes the kill-switch state and spare margin headroom "
        "vs the configured ``risk_max_position_pct``. Used by the Risk Simulator "
        "agent to short-circuit any insight that would breach hard limits."
    )
    args_schema: type[BaseModel] = PortfolioMarginInput

    def _run(  # type: ignore[override]
        self,
        session_id: str | None = None,
        include_positions: bool = True,
    ) -> str:
        try:
            from aqp.config import settings
            from aqp.persistence.db import get_session
            from aqp.risk.kill_switch import is_engaged
            from aqp.services.portfolio_service import compute_positions
        except Exception as exc:  # noqa: BLE001
            logger.exception("portfolio_margin imports failed")
            return json.dumps({"error": str(exc)})

        try:
            with get_session() as session:
                snapshot = compute_positions(session, session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("compute_positions failed")
            return json.dumps({"error": str(exc), "session_id": session_id})

        positions = snapshot.get("positions", []) if isinstance(snapshot, dict) else []
        cash = float(snapshot.get("cash", 0.0)) if isinstance(snapshot, dict) else 0.0
        equity = (
            float(snapshot.get("equity", 0.0)) if isinstance(snapshot, dict) else 0.0
        )

        gross_exposure = 0.0
        net_exposure = 0.0
        per_symbol: list[dict[str, Any]] = []
        cap_pct = float(getattr(settings, "risk_max_position_pct", 1.0) or 1.0)
        for pos in positions:
            try:
                qty = float(pos.get("quantity", 0.0))
                price = float(pos.get("market_price", pos.get("average_price", 0.0)))
                notional = qty * price
            except Exception:
                continue
            gross_exposure += abs(notional)
            net_exposure += notional
            pct = (abs(notional) / equity) if equity > 0 else 0.0
            row = {
                "vt_symbol": pos.get("vt_symbol"),
                "quantity": qty,
                "notional": notional,
                "position_pct": pct,
                "headroom_pct": max(0.0, cap_pct - pct),
            }
            per_symbol.append(row)

        result: dict[str, Any] = {
            "session_id": session_id,
            "cash": cash,
            "equity": equity,
            "gross_exposure": gross_exposure,
            "net_exposure": net_exposure,
            "leverage": (gross_exposure / equity) if equity > 0 else 0.0,
            "kill_switch_engaged": bool(is_engaged()),
            "max_position_pct": cap_pct,
            "max_drawdown_pct": float(
                getattr(settings, "risk_max_drawdown_pct", 0.0) or 0.0
            ),
        }
        if include_positions:
            result["positions"] = per_symbol
        return json.dumps(result, default=str)


__all__ = ["PortfolioMarginInput", "PortfolioMarginTool"]
