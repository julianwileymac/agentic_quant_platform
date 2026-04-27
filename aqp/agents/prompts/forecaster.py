"""Forecaster prompt templates ported from FinGPT.

Source: `FinGPT_Forecaster/prompt.py
<https://github.com/AI4Finance-Foundation/FinGPT/blob/master/fingpt/FinGPT_Forecaster/prompt.py>`_.
The original module hard-wired Finnhub + yfinance + the OpenAI Python
SDK; this version exposes only the **prompt-building** pieces so they
can be composed with AQP's ``router_complete`` LLM router (Ollama /
vLLM / OpenAI-compatible).

The output is a single instruction string ready to feed any tier-aware
LLM call. Callers supply the structured news / fundamentals / sentiment
fragments — this module concentrates the well-tuned phrasing that
empirically works for the FinGPT-Forecaster instruction-tuned models.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

EQUITY_PROMPT_END = (
    "\n\nBased on all the information before {start_date}, let's first analyze the "
    "positive developments and potential concerns for {symbol}. Come up with 2-4 most "
    "important factors respectively and keep them concise. Most factors should be "
    "inferred from company-related news. Then let's assume your prediction for next "
    "week ({start_date} to {end_date}) is {prediction}. Provide a summary analysis to "
    "support your prediction. The prediction result needs to be inferred from your "
    "analysis at the end, and thus not appearing as a foundational factor of your "
    "analysis."
)

CRYPTO_PROMPT_END = (
    "\n\nBased on all the information before {start_date}, let's first analyze the "
    "positive developments and potential concerns for {symbol}. Come up with 2-4 most "
    "important factors respectively and keep them concise. Most factors should be "
    "inferred from cryptocurrency-related news. Then let's assume your prediction for "
    "next week ({start_date} to {end_date}) is {prediction}. Provide a summary analysis "
    "to support your prediction. The prediction result needs to be inferred from your "
    "analysis at the end, and thus not appearing as a foundational factor of your "
    "analysis."
)


def map_bin_label(bin_lb: str) -> str:
    """Convert FinGPT-style ``U3`` / ``D5+`` labels into human prose.

    >>> map_bin_label("U2")
    'up by 1-2%'
    >>> map_bin_label("D5+")
    'down by more than 5%'
    """
    lb = str(bin_lb or "").replace("U", "up by ").replace("D", "down by ")
    lb = lb.replace("1", "0-1%").replace("2", "1-2%").replace("3", "2-3%").replace("4", "3-4%")
    if lb.endswith("+"):
        lb = lb.replace("5+", "more than 5%")
    else:
        lb = lb.replace("5", "4-5%")
    return lb


@dataclass
class ForecasterContext:
    """Optional context frame consumed by :func:`build_forecaster_prompt`."""

    company_intro: str = ""
    news_headlines: list[str] = None  # type: ignore[assignment]
    market_sentiment: str = ""
    basic_financials: str = ""
    history: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.news_headlines is None:
            self.news_headlines = []
        if self.history is None:
            self.history = []


def _format_history_block(history: Iterable[str]) -> str:
    items = [str(h).strip() for h in history if str(h).strip()]
    if not items:
        return ""
    return "\n\n".join(items)


def build_forecaster_prompt(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    prediction: str,
    context: ForecasterContext | None = None,
    asset_kind: str = "equity",
) -> str:
    """Assemble a FinGPT-style weekly forecaster prompt.

    Parameters
    ----------
    symbol:
        Ticker / instrument identifier.
    start_date / end_date:
        Forecast window in ``YYYY-MM-DD``.
    prediction:
        Pre-computed direction guess, e.g. ``"up by 1-2%"`` (use
        :func:`map_bin_label` to translate from the FinGPT bin labels).
    context:
        Optional :class:`ForecasterContext` carrying news, fundamentals,
        sentiment, and history blocks. Missing fields become ``None`` /
        empty.
    asset_kind:
        ``"equity"`` (default) or ``"crypto"`` — switches the closing
        instructions.
    """
    ctx = context or ForecasterContext()
    parts: list[str] = []
    if ctx.company_intro:
        parts.append(ctx.company_intro.strip())

    history_block = _format_history_block(ctx.history)
    if history_block:
        parts.append(history_block)

    if ctx.news_headlines:
        parts.append(
            f"News for {symbol} during the lookback period:\n"
            + "\n".join(f"- {h}" for h in ctx.news_headlines)
        )

    if ctx.market_sentiment:
        parts.append(ctx.market_sentiment.strip())

    if ctx.basic_financials:
        parts.append(ctx.basic_financials.strip())

    closing = (CRYPTO_PROMPT_END if asset_kind.lower() == "crypto" else EQUITY_PROMPT_END).format(
        start_date=start_date, end_date=end_date, prediction=prediction, symbol=symbol
    )
    parts.append(closing.strip())
    return "\n\n".join(parts)


__all__ = [
    "CRYPTO_PROMPT_END",
    "EQUITY_PROMPT_END",
    "ForecasterContext",
    "build_forecaster_prompt",
    "map_bin_label",
]
