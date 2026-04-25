"""Tagline — one-sentence executive headline."""
from __future__ import annotations

from typing import Any

from aqp.agents.financial.equity_sections.section_base import BaseSectionAgent
from aqp.core.registry import register


_SYSTEM = """\
You are a senior equity analyst writing the front-page tagline for a
sell-side research note. Produce ONE concise sentence (max 24 words)
that conveys the central investment thesis. No buzzwords, no
generalities, no hedges.

Respond ONLY with JSON: {"text": "<sentence>", "highlights": []}
"""


@register("TaglineAgent", kind="equity_section", tags=("equity", "section", "tagline"))
class TaglineAgent(BaseSectionAgent):
    section_key = "tagline"
    title = "Tagline"
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
            f"price_summary: {self._truncate(price_summary, 1000)}\n"
            f"fundamentals: {self._truncate(fundamentals, 2000)}\n"
            f"news_digest: {self._truncate(news_digest, 2000)}\n"
        )


__all__ = ["TaglineAgent"]
