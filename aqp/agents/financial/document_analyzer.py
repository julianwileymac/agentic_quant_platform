"""FinRobot Document Analyzer — SEC filings / transcripts summarisation + Q&A."""
from __future__ import annotations

import json
from typing import Any

from aqp.agents.financial.base import BaseFinancialCrew, FinancialReport
from aqp.core.registry import agent


_SYSTEM = """\
You are a financial-document analyst. Read the provided document (excerpt)
and answer the question exhaustively with citations to specific sentences
from the document.

Respond ONLY with JSON with keys:
  answer: string (detailed),
  quotes: [{text: string, section: string}],
  confidence: number (0..1),
  risks_flagged: [string]
"""


@agent("DocumentAnalyzerCrew", tags=("llm-crew", "document", "finrobot"))
class DocumentAnalyzer(BaseFinancialCrew):
    name = "document-analyzer"

    def run(
        self,
        *,
        document_excerpt: str,
        question: str,
        as_of: str = "",
        doc_name: str = "document",
        **_: Any,
    ) -> FinancialReport:
        user = (
            f"doc_name: {doc_name}\n"
            f"question: {question}\n"
            f"excerpt:\n{document_excerpt[:12000]}\n"
        )
        call = self._call(_SYSTEM, user, tier=self.tier)
        payload = call["payload"] or {}
        return FinancialReport(
            title=f"Document Analysis: {doc_name}",
            as_of=as_of,
            payload={
                "question": question,
                "answer": str(payload.get("answer", "")),
                "confidence": float(payload.get("confidence", 0.5) or 0.5),
                "risks_flagged": list(payload.get("risks_flagged", []) or []),
            },
            sections=[{"name": "citation", "body": q} for q in payload.get("quotes", [])],
            usage=self._usage([call]),
        )


__all__ = ["DocumentAnalyzer"]
