"""FinRobot Financial Report builder — assemble a full equity report."""
from __future__ import annotations

import json
from typing import Any

from aqp.agents.financial.base import BaseFinancialCrew, FinancialReport
from aqp.core.registry import agent


_SYSTEM = """\
You are an equity research writer. Given structured inputs (fundamentals,
sentiment, technicals, forecasts, document highlights) produce a polished
research report.

Respond ONLY with JSON:
  summary: string (1-2 sentences),
  recommendation: "BUY" | "HOLD" | "SELL",
  target_price: number | null,
  sections: [{heading: string, bullets: [string]}],
  risks: [string]
"""


@agent("FinancialReportBuilder", tags=("llm-crew", "research", "finrobot"))
class FinancialReportBuilder(BaseFinancialCrew):
    name = "financial-report"

    def run(
        self,
        *,
        ticker: str,
        as_of: str,
        fundamentals: dict[str, Any] | None = None,
        technicals: dict[str, Any] | None = None,
        sentiment: dict[str, Any] | None = None,
        forecasts: dict[str, Any] | None = None,
        document_highlights: list[dict[str, Any]] | None = None,
        **_: Any,
    ) -> FinancialReport:
        user = (
            f"ticker: {ticker}\n"
            f"as_of: {as_of}\n"
            f"fundamentals: {json.dumps(fundamentals or {}, default=str)[:4000]}\n"
            f"technicals:   {json.dumps(technicals   or {}, default=str)[:2000]}\n"
            f"sentiment:    {json.dumps(sentiment    or {}, default=str)[:2000]}\n"
            f"forecasts:    {json.dumps(forecasts    or {}, default=str)[:2000]}\n"
            f"document_highlights: {json.dumps(document_highlights or [], default=str)[:4000]}\n"
        )
        call = self._call(_SYSTEM, user, tier=self.tier)
        payload = call["payload"] or {}
        return FinancialReport(
            title=f"Equity Report: {ticker}",
            as_of=as_of,
            payload={
                "ticker": ticker,
                "summary": str(payload.get("summary", "")),
                "recommendation": str(payload.get("recommendation", "HOLD")),
                "target_price": payload.get("target_price"),
                "risks": list(payload.get("risks", []) or []),
            },
            sections=list(payload.get("sections", []) or []),
            usage=self._usage([call]),
        )


__all__ = ["FinancialReportBuilder"]
