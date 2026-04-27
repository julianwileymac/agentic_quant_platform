"""Reusable prompt templates for agentic trading."""

from aqp.agents.prompts.forecaster import (
    CRYPTO_PROMPT_END,
    EQUITY_PROMPT_END,
    build_forecaster_prompt,
    map_bin_label,
)

__all__ = [
    "CRYPTO_PROMPT_END",
    "EQUITY_PROMPT_END",
    "build_forecaster_prompt",
    "map_bin_label",
]
