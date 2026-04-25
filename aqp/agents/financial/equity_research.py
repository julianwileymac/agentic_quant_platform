"""FinRobot Equity Research meta-crew.

Chains :class:`MarketForecaster`, :class:`DocumentAnalyzer`, and
:class:`FinancialReportBuilder` into a single "give me a full equity
research package" call.
"""
from __future__ import annotations

from typing import Any

from aqp.agents.financial.base import BaseFinancialCrew, FinancialReport
from aqp.agents.financial.document_analyzer import DocumentAnalyzer
from aqp.agents.financial.financial_report import FinancialReportBuilder
from aqp.agents.financial.market_forecaster import MarketForecaster
from aqp.core.registry import agent


@agent("EquityResearchCrew", tags=("llm-crew", "research", "finrobot", "meta"))
class EquityResearch(BaseFinancialCrew):
    name = "equity-research"

    def run(
        self,
        *,
        ticker: str,
        as_of: str,
        fundamentals: dict[str, Any] | None = None,
        technicals: dict[str, Any] | None = None,
        sentiment: dict[str, Any] | None = None,
        news_digest: list[dict[str, Any]] | None = None,
        price_summary: dict[str, Any] | None = None,
        documents: list[tuple[str, str, str]] | None = None,  # (doc_name, question, excerpt)
        **_: Any,
    ) -> FinancialReport:
        sub_forecaster = MarketForecaster(provider=self.provider, model=self.model, tier=self.tier)
        sub_docs = DocumentAnalyzer(provider=self.provider, model=self.model, tier=self.tier)
        sub_builder = FinancialReportBuilder(provider=self.provider, model=self.model, tier=self.tier)

        forecast_report = sub_forecaster.run(
            ticker=ticker,
            as_of=as_of,
            price_summary=price_summary or {},
            fundamentals=fundamentals,
            news_digest=news_digest,
        )

        doc_reports: list[FinancialReport] = []
        for doc_name, question, excerpt in (documents or []):
            doc_reports.append(
                sub_docs.run(
                    document_excerpt=excerpt,
                    question=question,
                    as_of=as_of,
                    doc_name=doc_name,
                )
            )

        final = sub_builder.run(
            ticker=ticker,
            as_of=as_of,
            fundamentals=fundamentals,
            technicals=technicals,
            sentiment=sentiment,
            forecasts=forecast_report.payload,
            document_highlights=[r.payload for r in doc_reports],
        )

        usage_items = [forecast_report.usage, *[r.usage for r in doc_reports], final.usage]
        combined_usage = {
            "calls": sum(int(u.get("calls", 0) or 0) for u in usage_items),
            "prompt_tokens": sum(int(u.get("prompt_tokens", 0) or 0) for u in usage_items),
            "completion_tokens": sum(int(u.get("completion_tokens", 0) or 0) for u in usage_items),
            "cost_usd": sum(float(u.get("cost_usd", 0.0) or 0.0) for u in usage_items),
        }

        return FinancialReport(
            title=f"Equity Research: {ticker}",
            as_of=as_of,
            payload={
                "ticker": ticker,
                "summary": final.payload.get("summary", ""),
                "recommendation": final.payload.get("recommendation", "HOLD"),
                "target_price": final.payload.get("target_price"),
                "forecast": forecast_report.payload,
                "documents": [r.payload for r in doc_reports],
            },
            sections=final.sections,
            usage=combined_usage,
        )


__all__ = ["EquityResearch"]
