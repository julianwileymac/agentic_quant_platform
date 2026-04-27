"""Static catalog of built-in LLM providers.

Add a new provider by appending a :class:`ProviderSpec` to :data:`PROVIDERS`.
The router handles the rest.
"""
from __future__ import annotations

from aqp.llm.providers.base import ProviderSpec


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        slug="openai",
        litellm_prefix="openai/",
        env_key="OPENAI_API_KEY",
        settings_attr="openai_api_key",
        base_url_attr="openai_base_url",
        default_deep_model="gpt-5.4",
        default_quick_model="gpt-5.4-mini",
    ),
    "anthropic": ProviderSpec(
        slug="anthropic",
        litellm_prefix="anthropic/",
        env_key="ANTHROPIC_API_KEY",
        settings_attr="anthropic_api_key",
        default_deep_model="claude-4.6-sonnet",
        default_quick_model="claude-4.6-haiku",
    ),
    "google": ProviderSpec(
        slug="google",
        # LiteLLM uses ``gemini/`` for the public API.
        litellm_prefix="gemini/",
        env_key="GOOGLE_API_KEY",
        settings_attr="google_api_key",
        default_deep_model="gemini-3.1-pro",
        default_quick_model="gemini-3.1-flash",
    ),
    "xai": ProviderSpec(
        slug="xai",
        litellm_prefix="xai/",
        env_key="XAI_API_KEY",
        settings_attr="xai_api_key",
        default_deep_model="grok-4.1",
        default_quick_model="grok-4-mini",
    ),
    "deepseek": ProviderSpec(
        slug="deepseek",
        litellm_prefix="deepseek/",
        env_key="DEEPSEEK_API_KEY",
        settings_attr="deepseek_api_key",
        default_deep_model="deepseek-reasoner",
        default_quick_model="deepseek-chat",
    ),
    "groq": ProviderSpec(
        slug="groq",
        litellm_prefix="groq/",
        env_key="GROQ_API_KEY",
        settings_attr="groq_api_key",
        default_deep_model="llama-3.3-70b-versatile",
        default_quick_model="llama-3.3-70b-versatile",
    ),
    "openrouter": ProviderSpec(
        slug="openrouter",
        litellm_prefix="openrouter/",
        env_key="OPENROUTER_API_KEY",
        settings_attr="openrouter_api_key",
        default_deep_model="anthropic/claude-4.6-sonnet",
        default_quick_model="anthropic/claude-4.6-haiku",
    ),
    "ollama": ProviderSpec(
        slug="ollama",
        litellm_prefix="ollama/",
        env_key="",  # Ollama doesn't require an API key
        settings_attr="",
        base_url_attr="ollama_host",
        default_deep_model="nemotron:latest",
        default_quick_model="llama3.2:latest",
        requires_api_key=False,
    ),
    # vLLM exposes an OpenAI-compatible HTTP API; we proxy through LiteLLM's
    # ``openai/`` adapter pointed at ``vllm_base_url``. Works for both an
    # in-cluster vLLM service (docker compose ``vllm`` profile) and any
    # external vLLM endpoint a user runs themselves.
    "vllm": ProviderSpec(
        slug="vllm",
        litellm_prefix="openai/",
        env_key="AQP_VLLM_API_KEY",
        settings_attr="vllm_api_key",
        base_url_attr="vllm_base_url",
        default_deep_model="nemotron",
        default_quick_model="nemotron",
        requires_api_key=False,
    ),
}
