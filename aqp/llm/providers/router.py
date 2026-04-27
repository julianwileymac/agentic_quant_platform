"""Provider router — resolves ``(provider, model, tier)`` to a LiteLLM call.

Public entry points:

- :func:`get_provider` — look up a provider by slug, return a concrete
  :class:`LLMProvider` handle.
- :func:`resolve_model` — normalize an optional model string using the
  provider's defaults when the caller didn't specify one.
- :func:`router_complete` — one-shot completion through LiteLLM that
  records ``cost_usd`` on the returned :class:`LLMResult`.

The router is intentionally free of Pydantic validation so call sites
stay trivially mockable in tests (``mock.patch("aqp.llm.providers.router.router_complete")``).
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from aqp.config import settings
from aqp.llm.providers.base import LLMProvider, ProviderSpec
from aqp.llm.providers.catalog import PROVIDERS
from aqp.llm.tokens import compute_cost

logger = logging.getLogger(__name__)


class _DefaultProvider(LLMProvider):
    """Runtime handle built from a :class:`ProviderSpec`."""

    def __init__(self, spec: ProviderSpec) -> None:
        self.spec = spec

    def model_string(self, model: str) -> str:
        if not model:
            model = self.default_model("deep")
        if "/" in model:
            # Caller already supplied a fully-qualified id.
            return model
        return f"{self.spec.litellm_prefix}{model}"

    def api_key(self) -> str:
        if not self.spec.settings_attr:
            return ""
        key = getattr(settings, self.spec.settings_attr, "") or ""
        if key:
            return key
        # Fall back to the env var LiteLLM inspects natively.
        return os.environ.get(self.spec.env_key, "")

    def base_url(self) -> str:
        try:
            from aqp.runtime.control_plane import get_provider_control

            control = get_provider_control()
            if self.spec.slug == "ollama":
                override = str(control.get("ollama_host") or "").strip()
                if override:
                    return override
            if self.spec.slug == "vllm":
                override = str(control.get("vllm_base_url") or "").strip()
                if override:
                    return override
        except Exception:
            logger.debug("runtime provider control unavailable", exc_info=True)
        if not self.spec.base_url_attr:
            return ""
        return getattr(settings, self.spec.base_url_attr, "") or ""


_INSTANCES: dict[str, LLMProvider] = {}


def list_providers() -> list[str]:
    """Return slugs for every registered provider."""
    return sorted(PROVIDERS)


def get_provider(slug: str) -> LLMProvider:
    """Return the :class:`LLMProvider` registered under ``slug``.

    Raises ``KeyError`` if the slug isn't recognized so callers can
    surface a friendly "unknown provider" error in the UI.
    """
    slug = (slug or "").lower().strip()
    if slug not in PROVIDERS:
        raise KeyError(
            f"Unknown LLM provider: {slug!r}. "
            f"Available providers: {', '.join(list_providers())}"
        )
    if slug not in _INSTANCES:
        _INSTANCES[slug] = _DefaultProvider(PROVIDERS[slug])
    return _INSTANCES[slug]


@dataclass
class LLMResult:
    """Outcome of a single completion call."""

    content: str
    model: str
    provider: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    raw: Any = None


def resolve_model(provider: LLMProvider, model: str | None, tier: str = "deep") -> str:
    """Return a concrete model id for ``provider`` and ``tier``.

    - ``None`` / empty → provider's tier default.
    - Bare id (``"claude-4.6-haiku"``) → prefix added.
    - Fully-qualified id (``"anthropic/claude-4.6-haiku"``) → passed through.
    """
    bare = (model or "").strip()
    if not bare:
        bare = provider.default_model(tier)
    return provider.model_string(bare)


def _require_key(provider: LLMProvider) -> None:
    if not provider.spec.requires_api_key:
        return
    if not provider.api_key():
        raise RuntimeError(
            f"LLM provider {provider.spec.slug!r} requires an API key. "
            f"Set AQP_{provider.spec.settings_attr.upper()} (or the "
            f"{provider.spec.env_key} env var) before calling the crew."
        )


def router_complete(
    provider: str,
    model: str,
    prompt: str | None = None,
    messages: Iterable[dict[str, str]] | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> LLMResult:
    """One-shot completion through LiteLLM that also records USD cost."""
    import litellm

    litellm.drop_params = True

    handle = get_provider(provider)
    _require_key(handle)
    full_model = resolve_model(handle, model, tier=extra.pop("tier", "deep"))

    msgs = (
        list(messages)
        if messages
        else [{"role": "user", "content": prompt or ""}]
    )

    # Per-provider connection kwargs. LiteLLM accepts ``api_base`` to
    # override the endpoint (Ollama + Azure) and ``api_key`` for providers
    # we wrangle outside env vars.
    call_kwargs: dict[str, Any] = dict(extra)
    base_url = handle.base_url()
    if base_url:
        call_kwargs.setdefault("api_base", base_url)
    key = handle.api_key()
    if key:
        call_kwargs.setdefault("api_key", key)
    elif handle.spec.slug == "vllm" and base_url:
        # vLLM speaks OpenAI-compatible HTTP but doesn't require a real
        # API key. LiteLLM's ``openai/`` adapter still validates the key
        # is present, so pass a placeholder so calls go through.
        call_kwargs.setdefault("api_key", "EMPTY")

    response = litellm.completion(
        model=full_model,
        messages=msgs,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        timeout=settings.llm_request_timeout,
        **call_kwargs,
    )

    try:
        content = response["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        content = ""

    usage = response.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    cost = compute_cost(full_model, prompt_tokens, completion_tokens)

    return LLMResult(
        content=content,
        model=full_model,
        provider=handle.spec.slug,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost,
        raw=response,
    )
