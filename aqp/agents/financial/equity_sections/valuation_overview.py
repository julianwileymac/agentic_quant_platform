"""Valuation overview — multiples, DCF summary, target."""
from __future__ import annotations

from typing import Any

from aqp.agents.financial.equity_sections.section_base import BaseSectionAgent
from aqp.core.registry import register


_SYSTEM = """\
You are a valuation analyst writing the Valuation Overview section.
Discuss:

1. Current multiples vs peers and own history (P/E, EV/EBITDA, P/S).
2. Key inputs to a DCF (revenue growth, margin, terminal multiple).
3. A reasonable price target with a plus/minus range, with caveats.

Use the supplied valuation_inputs JSON when available; otherwise reason
from the fundamentals snapshot. Be quantitative — no hand-waving.

Respond ONLY with JSON:
  {"text": "<paragraphs>", "highlights": ["multiple vs peers", "DCF input", "target"]}
"""


@register(
    "ValuationOverviewAgent",
    kind="equity_section",
    tags=("equity", "section", "valuation"),
)
class ValuationOverviewAgent(BaseSectionAgent):
    section_key = "valuation_overview"
    title = "Valuation Overview"
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
        valuation = (extras or {}).get("valuation_inputs", {})
        return (
            f"ticker: {ticker}\n"
            f"as_of: {as_of}\n"
            f"price_summary: {self._truncate(price_summary, 2000)}\n"
            f"fundamentals: {self._truncate(fundamentals, 3000)}\n"
            f"valuation_inputs: {self._truncate(valuation, 2000)}\n"
            f"peers: {peers or []}\n"
        )


__all__ = ["ValuationOverviewAgent"]
