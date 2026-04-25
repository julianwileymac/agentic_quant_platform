"""Competitor analysis — peer comparison commentary."""
from __future__ import annotations

from typing import Any

from aqp.agents.financial.equity_sections.section_base import BaseSectionAgent
from aqp.core.registry import register


_SYSTEM = """\
You are an equity research analyst writing the Competitor Analysis
section. Compare the focus name against the supplied peer list across:

- Growth and margin trajectory
- Capital efficiency (ROIC, asset turn)
- Valuation multiples
- Strategic positioning and moat strength

Identify the closest competitor and call out any clear winners /
losers in the cohort.

Respond ONLY with JSON:
  {"text": "<paragraphs>", "highlights": ["closest peer", "winner", "loser"]}
"""


@register(
    "CompetitorAnalysisAgent",
    kind="equity_section",
    tags=("equity", "section", "peers"),
)
class CompetitorAnalysisAgent(BaseSectionAgent):
    section_key = "competitor_analysis"
    title = "Competitor Analysis"
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
        peer_data = (extras or {}).get("peer_fundamentals", {})
        return (
            f"focus: {ticker}\n"
            f"peers: {peers or []}\n"
            f"as_of: {as_of}\n"
            f"focus_fundamentals: {self._truncate(fundamentals, 3000)}\n"
            f"peer_fundamentals: {self._truncate(peer_data, 4000)}\n"
        )


__all__ = ["CompetitorAnalysisAgent"]
