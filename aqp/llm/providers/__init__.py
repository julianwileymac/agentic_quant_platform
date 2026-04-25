"""Multi-provider LLM layer — TradingAgents-style provider routing.

LiteLLM underpins every call, so from the application's perspective there is
a single ``complete`` / ``get_crewai_llm`` API regardless of whether the
configured provider is OpenAI, Anthropic, Google, xAI, DeepSeek, Groq,
OpenRouter, or Ollama.

Each concrete :class:`LLMProvider` knows:

- its LiteLLM **prefix** (e.g. ``openai/``) and which env var / settings
  field holds the API key;
- an optional **base_url** override (for OpenAI-compatible proxies);
- a list of **default models** for the ``deep`` / ``quick`` tiers so the
  router can resolve generic names like ``"deep"`` to a concrete model id.

Call sites should use :func:`aqp.llm.deep_llm` / :func:`aqp.llm.quick_llm`
or :func:`aqp.llm.get_crewai_llm` — those pick the provider from
:mod:`aqp.config.settings`. Only low-level code that needs explicit control
imports from this module directly.
"""
from __future__ import annotations

from aqp.llm.providers.base import LLMProvider, ProviderSpec
from aqp.llm.providers.router import (
    get_provider,
    list_providers,
    resolve_model,
    router_complete,
)

__all__ = [
    "LLMProvider",
    "ProviderSpec",
    "get_provider",
    "list_providers",
    "resolve_model",
    "router_complete",
]
