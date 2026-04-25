"""Company overview — business model, segments, geography."""
from __future__ import annotations

from typing import Any

from aqp.agents.financial.equity_sections.section_base import BaseSectionAgent
from aqp.core.registry import register


_SYSTEM = """\
You are an equity research analyst writing the Company Overview section.
Cover, in 2-3 short paragraphs:

1. What the company does (business model, primary product/service).
2. Revenue mix by segment / geography (use fundamentals if provided).
3. Strategic moat or competitive advantage (one sentence).

Respond ONLY with JSON:
  {"text": "<paragraphs>", "highlights": ["bullet 1", "bullet 2", ...]}
"""


@register("CompanyOverviewAgent", kind="equity_section", tags=("equity", "section", "overview"))
class CompanyOverviewAgent(BaseSectionAgent):
    section_key = "company_overview"
    title = "Company Overview"
    system_prompt = _SYSTEM

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
        return (
            f"ticker: {ticker}\n"
            f"as_of: {as_of}\n"
            f"fundamentals: {self._truncate(fundamentals, 4000)}\n"
            f"peers: {peers or []}\n"
            f"extras: {self._truncate(extras, 1500)}\n"
        )


__all__ = ["CompanyOverviewAgent"]
