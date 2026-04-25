"""Major takeaways — final 3-bullet TL;DR."""
from __future__ import annotations

from typing import Any

from aqp.agents.financial.equity_sections.section_base import BaseSectionAgent
from aqp.core.registry import register


_SYSTEM = """\
You are the senior PM signing off the research note. Produce exactly
THREE crisp takeaways an investor would walk away with. Bullets only,
no preamble.

Respond ONLY with JSON:
  {"text": "", "highlights": ["bullet 1", "bullet 2", "bullet 3"]}
"""


@register(
    "MajorTakeawaysAgent",
    kind="equity_section",
    tags=("equity", "section", "summary"),
)
class MajorTakeawaysAgent(BaseSectionAgent):
    section_key = "major_takeaways"
    title = "Major Takeaways"
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
        upstream = (extras or {}).get("section_summaries") or {}
        return (
            f"ticker: {ticker}\n"
            f"as_of: {as_of}\n"
            f"section_summaries: {self._truncate(upstream, 6000)}\n"
        )


__all__ = ["MajorTakeawaysAgent"]
