"""Abstract ``LLMProvider`` contract used by the router.

Each provider is a thin specification — it knows how to format a model id
for LiteLLM, where to find the API key, and whether a custom base URL is
needed. Concrete providers live in :mod:`aqp.llm.providers.catalog` and
are deliberately tiny so adding a new one is a single dict entry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    """Declarative description of one LLM provider.

    Attributes:
        slug: Short id used by config + CLI (``openai``, ``anthropic``, ...).
        litellm_prefix: Prefix LiteLLM expects (e.g. ``openai/``).
        env_key: Environment variable name that holds the API key when
            LiteLLM reads it directly; set alongside ``settings_attr`` so
            callers can fall back.
        settings_attr: Name of the attribute on :class:`aqp.config.Settings`
            that stores the API key in our own config surface.
        base_url_attr: Name of the settings attribute that overrides the
            provider's base URL (``""`` means LiteLLM picks its default).
        default_deep_model: Preferred model for the ``deep`` tier.
        default_quick_model: Preferred model for the ``quick`` tier.
        requires_api_key: Whether absence of a key should raise early.
    """

    slug: str
    litellm_prefix: str
    env_key: str
    settings_attr: str
    base_url_attr: str = ""
    default_deep_model: str = ""
    default_quick_model: str = ""
    requires_api_key: bool = True


class LLMProvider(ABC):
    """Runtime handle wrapping a :class:`ProviderSpec`.

    Providers are singletons discovered via :func:`aqp.llm.providers.get_provider`.
    Subclasses are optional — the default implementation in
    :mod:`aqp.llm.providers.router` covers every LiteLLM-compatible
    provider. This ABC exists so callers can type-annotate and so teams
    can swap in a bespoke client when they need to (e.g. Azure OpenAI or
    AWS Bedrock).
    """

    spec: ProviderSpec

    @abstractmethod
    def model_string(self, model: str) -> str:
        """Return the full LiteLLM model id (prefix + bare id)."""

    @abstractmethod
    def api_key(self) -> str:
        """Return the configured API key (may be empty for local providers)."""

    @abstractmethod
    def base_url(self) -> str:
        """Return the configured base URL (may be empty for hosted APIs)."""

    def default_model(self, tier: str) -> str:
        """Return the default model for the given tier (``deep`` | ``quick``)."""
        if tier == "quick":
            return self.spec.default_quick_model or self.spec.default_deep_model
        return self.spec.default_deep_model or self.spec.default_quick_model
