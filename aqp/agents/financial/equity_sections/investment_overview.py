"""Investment overview — bull thesis, growth drivers, conviction."""
from __future__ import annotations

from typing import Any

from aqp.agents.financial.equity_sections.section_base import BaseSectionAgent
from aqp.core.registry import register


_SYSTEM = """\
You are a senior equity research analyst writing the Investment
Overview section. In 2-4 paragraphs:

1. Articulate the central bull thesis.
2. Identify 2-3 growth drivers and quantify them where possible.
3. State the time horizon and the catalyst that would prove the thesis.

Be specific. Avoid clichés.

Respond ONLY with JSON:
  {"text": "<paragraphs>", "highlights": ["thesis", "driver 1", "driver 2", "catalyst"]}
"""


@register(
    "InvestmentOverviewAgent",
    kind="equity_section",
    tags=("equity", "section", "thesis"),
)
class InvestmentOverviewAgent(BaseSectionAgent):
    section_key = "investment_overview"
    title = "Investment Overview"
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
            f"price_summary: {self._truncate(price_summary, 2000)}\n"
            f"fundamentals: {self._truncate(fundamentals, 4000)}\n"
            f"news_digest: {self._truncate(news_digest, 3000)}\n"
            f"peers: {peers or []}\n"
        )


__all__ = ["InvestmentOverviewAgent"]
