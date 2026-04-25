"""Token cost accounting for multi-provider LLM calls.

LiteLLM ships its own cost table (``litellm.model_cost``) but it doesn't
cover every provider we use and the naming isn't always consistent with
the model id we send over the wire. This module keeps a pinned table
of USD / 1K tokens for the models the trader crew exercises so every
``LLMResult`` can carry a ``cost_usd`` field — critical for the
Quickstart Wizard's cost preview and for the ``AgentBacktest`` sidecar.

All prices are **input / output per 1K tokens** in USD as of Apr 2026.
Update the constant when your contracts change.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PricePer1K:
    """USD per 1,000 tokens for a single model."""

    input_usd: float
    output_usd: float

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens / 1000.0) * self.input_usd + (
            completion_tokens / 1000.0
        ) * self.output_usd


# Default price applied when we don't have an exact match. Zero so self-hosted
# models (Ollama) register as "free" which is correct for the user's wallet.
_ZERO = PricePer1K(0.0, 0.0)


# Canonical catalogue. Keys are lower-cased model ids **without** provider
# prefix. LiteLLM model strings look like ``openai/gpt-4o-mini`` so we strip
# the prefix when looking up.
CATALOG: dict[str, PricePer1K] = {
    # --- OpenAI (2026 pricing) ---
    "gpt-5.4": PricePer1K(0.0030, 0.0120),
    "gpt-5.4-mini": PricePer1K(0.00020, 0.00080),
    "gpt-5": PricePer1K(0.0025, 0.0100),
    "gpt-5-mini": PricePer1K(0.00018, 0.00070),
    "gpt-4o": PricePer1K(0.0025, 0.0100),
    "gpt-4o-mini": PricePer1K(0.00015, 0.00060),
    "gpt-4-turbo": PricePer1K(0.0100, 0.0300),
    "o1-mini": PricePer1K(0.00110, 0.00440),
    "o3-mini": PricePer1K(0.00110, 0.00440),
    # --- Anthropic ---
    "claude-4.6-sonnet": PricePer1K(0.0030, 0.0150),
    "claude-4.6-opus": PricePer1K(0.0150, 0.0750),
    "claude-4.6-haiku": PricePer1K(0.00025, 0.00125),
    "claude-4.5-sonnet": PricePer1K(0.0030, 0.0150),
    "claude-4.5-haiku": PricePer1K(0.00025, 0.00125),
    "claude-3-5-sonnet-20241022": PricePer1K(0.0030, 0.0150),
    "claude-3-5-haiku-20241022": PricePer1K(0.00080, 0.00400),
    "claude-3-opus-20240229": PricePer1K(0.0150, 0.0750),
    # --- Google ---
    "gemini-3.1-pro": PricePer1K(0.00125, 0.00500),
    "gemini-3.1-flash": PricePer1K(0.00008, 0.00030),
    "gemini-2.0-pro": PricePer1K(0.00125, 0.00500),
    "gemini-2.0-flash": PricePer1K(0.00007, 0.00028),
    # --- xAI ---
    "grok-4.1": PricePer1K(0.0050, 0.0150),
    "grok-4-mini": PricePer1K(0.0006, 0.0012),
    # --- DeepSeek ---
    "deepseek-chat": PricePer1K(0.00027, 0.00110),
    "deepseek-reasoner": PricePer1K(0.00055, 0.00220),
    # --- Groq (cheap inference; prices per Groq cloud 2026) ---
    "llama-3.3-70b-versatile": PricePer1K(0.00059, 0.00079),
    "mixtral-8x7b-32768": PricePer1K(0.00024, 0.00024),
    # --- OpenRouter: prices set at call time; default to zero and let LiteLLM
    # surface the authoritative ``usage.total_cost`` when present.
}


def canonical(model: str) -> str:
    """Normalize a model id (strip provider prefix, lowercase)."""
    m = model.lower()
    if "/" in m:
        m = m.split("/", 1)[1]
    return m


def price_for(model: str) -> PricePer1K:
    """Look up the price table row for ``model`` (prefix is stripped)."""
    return CATALOG.get(canonical(model), _ZERO)


def compute_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Compute USD cost for a single completion using :data:`CATALOG`."""
    return price_for(model).cost(prompt_tokens, completion_tokens)
