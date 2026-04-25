"""News summary — recent-window digest of relevant headlines."""
from __future__ import annotations

from typing import Any

from aqp.agents.financial.equity_sections.section_base import BaseSectionAgent
from aqp.core.registry import register


_SYSTEM = """\
You are a financial news editor. From the supplied news digest,
produce:

1. A 4-6 sentence narrative summarising the last 30 days of news for
   the focus ticker.
2. Up to 5 highlight bullets, each tagged with [POS], [NEG], or
   [NEUT] sentiment indicators.

Drop generic headlines that don't move the thesis. Do not invent
content.

Respond ONLY with JSON:
  {"text": "<narrative>", "highlights": ["[POS] ...", "[NEG] ..."]}
"""


@register("NewsSummaryAgent", kind="equity_section", tags=("equity", "section", "news"))
class NewsSummaryAgent(BaseSectionAgent):
    section_key = "news_summary"
    title = "News Summary"
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
            f"news_digest: {self._truncate(news_digest, 8000)}\n"
        )


__all__ = ["NewsSummaryAgent"]
