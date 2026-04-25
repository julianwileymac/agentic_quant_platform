"""Multi-provider LLM client (historically Ollama-only).

Exposes two tier helpers inspired by TradingAgents' ``deep_thinking_llm`` /
``quick_thinking_llm``:

- :func:`deep_llm`: slow, precise, used by judges / hypothesis design
- :func:`quick_llm`: fast, used by analysts / tool routing

Both dispatch through :mod:`aqp.llm.providers.router`, which routes the
call via LiteLLM to the provider configured in
:data:`aqp.config.settings.llm_provider` (default ``ollama``).

The public API — ``deep_llm``, ``quick_llm``, ``LLMResult``,
``get_crewai_llm``, ``check_health``, ``list_local_models`` — is
preserved so every existing caller keeps working.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from aqp.config import settings
from aqp.llm.providers.router import (
    LLMResult,
    get_provider,
    resolve_model,
    router_complete,
)

logger = logging.getLogger(__name__)


def _tier_defaults(tier: str) -> tuple[str, str, float]:
    """Return ``(provider_slug, model, temperature)`` for a tier.

    ``tier`` is ``"deep"`` or ``"quick"``. When the matching provider /
    model / temperature field is empty we fall back to the global
    defaults so simple deployments only need to set ``AQP_LLM_PROVIDER``
    and their keys.
    """
    tier = (tier or "deep").lower()
    if tier == "quick":
        return (
            settings.provider_for_tier("quick"),
            settings.llm_quick_model,
            settings.llm_temperature_quick,
        )
    return (
        settings.provider_for_tier("deep"),
        settings.llm_deep_model,
        settings.llm_temperature_deep,
    )


def complete(
    tier: str,
    prompt: str | None = None,
    messages: Iterable[dict[str, str]] | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> LLMResult:
    """Tier-aware completion. Thin wrapper around :func:`router_complete`."""
    default_provider, default_model, default_temp = _tier_defaults(tier)
    return router_complete(
        provider=(provider or default_provider),
        model=(model or default_model),
        prompt=prompt,
        messages=messages,
        temperature=(default_temp if temperature is None else temperature),
        max_tokens=max_tokens,
        tools=tools,
        tier=tier,
        **extra,
    )


def deep_llm(
    prompt: str | None = None,
    messages: Iterable[dict[str, str]] | None = None,
    **kw: Any,
) -> LLMResult:
    """Slow-but-precise tier. Used for judges and hypothesis formulation."""
    return complete("deep", prompt=prompt, messages=messages, **kw)


def quick_llm(
    prompt: str | None = None,
    messages: Iterable[dict[str, str]] | None = None,
    **kw: Any,
) -> LLMResult:
    """Fast, cheap tier. Used for analyst steps and tool routing."""
    return complete("quick", prompt=prompt, messages=messages, **kw)


def check_health() -> bool:
    """Lightweight health check for the Ollama host when it's in use.

    Only meaningful when the active provider is ``ollama``; always returns
    ``True`` for hosted providers because a real HTTP ping requires an
    API key we don't want to burn here.
    """
    provider_slug = settings.provider_for_tier("deep")
    if provider_slug != "ollama":
        return True

    import httpx

    try:
        r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def list_local_models() -> list[str]:
    """Enumerate locally-installed Ollama models.

    Returns an empty list when the active provider isn't Ollama so the
    UI's model picker can fall through to the provider's default catalog.
    """
    provider_slug = settings.provider_for_tier("deep")
    if provider_slug != "ollama":
        return []

    import httpx

    try:
        r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=5.0)
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def get_crewai_llm(tier: str = "deep", *, provider: str | None = None, model: str | None = None):
    """Return a CrewAI-compatible LLM object routed to the active provider.

    CrewAI uses LiteLLM underneath, so we expose a thin wrapper over
    ``crewai.LLM`` that plugs in the same ``model_string`` /
    ``api_base`` / ``api_key`` triple the router computes.
    """
    from crewai import LLM

    default_provider, default_model, default_temp = _tier_defaults(tier)
    handle = get_provider(provider or default_provider)
    resolved_model = resolve_model(handle, (model or default_model), tier=tier)

    kwargs: dict[str, Any] = {
        "model": resolved_model,
        "temperature": default_temp,
    }
    base_url = handle.base_url()
    if base_url:
        kwargs["base_url"] = base_url
    key = handle.api_key()
    if key:
        kwargs["api_key"] = key
    return LLM(**kwargs)


__all__ = [
    "LLMResult",
    "check_health",
    "complete",
    "deep_llm",
    "get_crewai_llm",
    "list_local_models",
    "quick_llm",
]
