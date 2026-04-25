"""Risks — concise bullets covering principal hazards."""
from __future__ import annotations

from typing import Any

from aqp.agents.financial.equity_sections.section_base import BaseSectionAgent
from aqp.core.registry import register


_SYSTEM = """\
You are an equity risk analyst. Produce 4-6 succinct bullet risks for
the named ticker, drawing on the fundamentals + news digest. Cover:

- Macro / cyclical exposure
- Competitive / disruption risks
- Regulatory / legal risks
- Idiosyncratic execution / governance risks

Each bullet must be a single sentence. No padding.

Respond ONLY with JSON:
  {"text": "<one short framing paragraph>", "highlights": ["bullet 1", ...]}
"""


@register("RisksAgent", kind="equity_section", tags=("equity", "section", "risk"))
class RisksAgent(BaseSectionAgent):
    section_key = "risks"
    title = "Risks"
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
            f"fundamentals: {self._truncate(fundamentals, 3000)}\n"
            f"news_digest: {self._truncate(news_digest, 4000)}\n"
        )


__all__ = ["RisksAgent"]
