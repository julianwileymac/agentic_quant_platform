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

This module also exposes lifecycle helpers used by the LLM control plane:
:func:`pull_model`, :func:`delete_model` and :func:`list_running_models`.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from typing import Any

from aqp.config import settings
from aqp.llm.providers.router import (
    LLMResult,
    get_provider,
    resolve_model,
    router_complete,
)

logger = logging.getLogger(__name__)


def _ollama_host() -> str:
    """Return the active Ollama host, honouring runtime overrides."""
    try:
        from aqp.runtime.control_plane import get_provider_control

        host = (get_provider_control().get("ollama_host") or "").strip()
        if host:
            return host.rstrip("/")
    except Exception:  # pragma: no cover
        logger.debug("could not read provider control", exc_info=True)
    return (settings.ollama_host or "").rstrip("/")


def _runtime_llm_control() -> dict[str, str]:
    try:
        from aqp.runtime.control_plane import get_provider_control

        blob = get_provider_control()
        return {
            "provider": str(blob.get("provider") or "").strip().lower(),
            "deep_model": str(blob.get("deep_model") or "").strip(),
            "quick_model": str(blob.get("quick_model") or "").strip(),
            "ollama_host": str(blob.get("ollama_host") or "").strip(),
            "vllm_base_url": str(blob.get("vllm_base_url") or "").strip(),
        }
    except Exception:
        return {
            "provider": "",
            "deep_model": "",
            "quick_model": "",
            "ollama_host": "",
            "vllm_base_url": "",
        }


def _tier_defaults(tier: str) -> tuple[str, str, float]:
    """Return ``(provider_slug, model, temperature)`` for a tier.

    ``tier`` is ``"deep"`` or ``"quick"``. When the matching provider /
    model / temperature field is empty we fall back to the global
    defaults so simple deployments only need to set ``AQP_LLM_PROVIDER``
    and their keys.
    """
    tier = (tier or "deep").lower()
    control = _runtime_llm_control()
    runtime_provider = control.get("provider") or ""
    if tier == "quick":
        provider = runtime_provider or settings.provider_for_tier("quick")
        return (
            provider,
            control.get("quick_model") or settings.llm_quick_model,
            settings.llm_temperature_quick,
        )
    provider = runtime_provider or settings.provider_for_tier("deep")
    return (
        provider,
        control.get("deep_model") or settings.llm_deep_model,
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
    control = _runtime_llm_control()
    provider_slug = control.get("provider") or settings.provider_for_tier("deep")
    if provider_slug != "ollama":
        return True

    import httpx

    host = control.get("ollama_host") or settings.ollama_host
    try:
        r = httpx.get(f"{host}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def list_local_models(*, host: str | None = None) -> list[str]:
    """Enumerate locally-installed Ollama models.

    The host is read from runtime control plane / settings unless
    overridden. Returns an empty list if the host is unreachable.
    """
    target = (host or _ollama_host()).rstrip("/")
    if not target:
        return []

    import httpx

    try:
        r = httpx.get(f"{target}/api/tags", timeout=5.0)
        r.raise_for_status()
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def pull_model(name: str, *, host: str | None = None) -> Iterator[dict[str, Any]]:
    """Stream Ollama ``/api/pull`` events for ``name``.

    Yields dicts with keys like ``status``, ``digest``, ``total``,
    ``completed`` so callers can render a progress bar. Raises a
    ``RuntimeError`` if the host is unreachable.
    """
    import httpx

    target = (host or _ollama_host()).rstrip("/")
    if not target:
        raise RuntimeError("ollama host is not configured")
    payload = {"name": str(name).strip(), "stream": True}
    try:
        with httpx.stream(
            "POST", f"{target}/api/pull", json=payload, timeout=None
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:  # noqa: PERF203
                    yield {"status": str(line)}
    except httpx.HTTPError as exc:
        raise RuntimeError(f"ollama pull failed: {exc}") from exc


def delete_model(name: str, *, host: str | None = None) -> bool:
    """Delete a local Ollama model by tag. Returns ``True`` on success."""
    import httpx

    target = (host or _ollama_host()).rstrip("/")
    if not target:
        raise RuntimeError("ollama host is not configured")
    try:
        resp = httpx.request(
            "DELETE",
            f"{target}/api/delete",
            json={"name": str(name).strip()},
            timeout=30.0,
        )
        return resp.status_code in {200, 204}
    except httpx.HTTPError as exc:  # pragma: no cover
        logger.warning("ollama delete failed: %s", exc)
        return False


def list_running_models(*, host: str | None = None) -> list[dict[str, Any]]:
    """Return the list of models currently loaded in Ollama (``/api/ps``)."""
    import httpx

    target = (host or _ollama_host()).rstrip("/")
    if not target:
        return []
    try:
        resp = httpx.get(f"{target}/api/ps", timeout=5.0)
        resp.raise_for_status()
        data = resp.json() or {}
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for model in data.get("models", []) or []:
        if not isinstance(model, dict):
            continue
        out.append(
            {
                "name": str(model.get("name") or ""),
                "size": int(model.get("size") or 0),
                "digest": str(model.get("digest") or ""),
                "expires_at": str(model.get("expires_at") or ""),
            }
        )
    return out


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
    "delete_model",
    "get_crewai_llm",
    "list_local_models",
    "list_running_models",
    "pull_model",
    "quick_llm",
]
