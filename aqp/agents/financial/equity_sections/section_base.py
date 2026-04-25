"""Shared base class for FinRobot-style section agents."""
from __future__ import annotations

import json
import logging
from abc import abstractmethod
from typing import Any

from aqp.agents.financial.base import BaseFinancialCrew, FinancialReport

logger = logging.getLogger(__name__)


class BaseSectionAgent(BaseFinancialCrew):
    """One section of an equity research report.

    Subclasses set:

    - ``section_key`` — stable identifier (``"tagline"``, ...).
    - ``title`` — human-readable section title.
    - ``system_prompt`` — LLM system prompt; should ask for JSON output
      with shape ``{"text": "...", "highlights": [...]}``.
    """

    section_key: str = "section"
    title: str = "Section"
    system_prompt: str = "You are an equity analyst. Respond with JSON {text, highlights}."

    name = "equity-section"

    @abstractmethod
    def build_user(
        self,
        *,
        ticker: str,
        as_of: str,
        price_summary: dict[str, Any] | None,
        fundamentals: dict[str, Any] | None,
        news_digest: list[dict[str, Any]] | None,
        peers: list[str] | None,
        extras: dict[str, Any] | None,
    ) -> str:
        """Return the user-message body for this section."""

    def run(
        self,
        *,
        ticker: str,
        as_of: str,
        price_summary: dict[str, Any] | None = None,
        fundamentals: dict[str, Any] | None = None,
        news_digest: list[dict[str, Any]] | None = None,
        peers: list[str] | None = None,
        extras: dict[str, Any] | None = None,
        **_: Any,
    ) -> FinancialReport:
        user = self.build_user(
            ticker=ticker,
            as_of=as_of,
            price_summary=price_summary,
            fundamentals=fundamentals,
            news_digest=news_digest,
            peers=peers,
            extras=extras,
        )
        try:
            call = self._call(self.system_prompt, user, tier=self.tier)
        except Exception:
            logger.exception("section %s LLM call failed", self.section_key)
            return FinancialReport(
                title=self.title,
                as_of=as_of,
                payload={
                    "section_key": self.section_key,
                    "ticker": ticker,
                    "text": "",
                    "highlights": [],
                    "error": "llm_call_failed",
                },
                sections=[],
                usage={"calls": 0, "cost_usd": 0.0},
            )
        payload: dict[str, Any] = call.get("payload") or {}
        text = str(payload.get("text") or payload.get("body") or call.get("content") or "")
        highlights = payload.get("highlights") or payload.get("bullets") or []
        if isinstance(highlights, str):
            highlights = [h.strip() for h in highlights.splitlines() if h.strip()]
        return FinancialReport(
            title=self.title,
            as_of=as_of,
            payload={
                "section_key": self.section_key,
                "ticker": ticker,
                "text": text,
                "highlights": list(highlights),
                "raw": payload,
            },
            sections=[{"name": self.section_key, "body": text}],
            usage=self._usage([call]),
        )

    @staticmethod
    def _truncate(payload: Any, length: int = 3000) -> str:
        return json.dumps(payload or {}, default=str)[:length]


__all__ = ["BaseSectionAgent"]
