"""FinRobot Trade Strategist — turn a decision into an execution plan."""
from __future__ import annotations

import json
from typing import Any

from aqp.agents.financial.base import BaseFinancialCrew, FinancialReport
from aqp.core.registry import agent


_SYSTEM = """\
You are a systematic trade strategist. Given a structured trade idea
(symbol, direction, size, horizon, rationale) and current market context
(liquidity, ADV, bid/ask), produce an execution plan.

Respond ONLY with JSON:
  entry:     {price_ref: "mid"|"vwap"|"limit", offset_bps: number, slice_minutes: number},
  take_profit: {pct: number, method: "single" | "scale-out"},
  stop_loss:   {pct: number, trailing: boolean},
  risk_bracket:{max_position_pct: number, max_loss_pct: number},
  notes: [string]
"""


@agent("TradeStrategistCrew", tags=("llm-crew", "execution", "finrobot"))
class TradeStrategist(BaseFinancialCrew):
    name = "trade-strategist"

    def run(
        self,
        *,
        symbol: str,
        as_of: str,
        decision: dict[str, Any],
        market_context: dict[str, Any] | None = None,
        **_: Any,
    ) -> FinancialReport:
        user = (
            f"symbol: {symbol}\n"
            f"as_of: {as_of}\n"
            f"decision: {json.dumps(decision, default=str)}\n"
            f"market_context: {json.dumps(market_context or {}, default=str)}\n"
        )
        call = self._call(_SYSTEM, user, tier=self.tier)
        payload = call["payload"] or {}
        return FinancialReport(
            title=f"Trade Plan: {symbol}",
            as_of=as_of,
            payload={
                "symbol": symbol,
                "entry": payload.get("entry", {}),
                "take_profit": payload.get("take_profit", {}),
                "stop_loss": payload.get("stop_loss", {}),
                "risk_bracket": payload.get("risk_bracket", {}),
            },
            sections=[{"name": "notes", "body": payload.get("notes", [])}],
            usage=self._usage([call]),
        )


__all__ = ["TradeStrategist"]
