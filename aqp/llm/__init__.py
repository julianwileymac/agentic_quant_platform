"""LLM layer — multi-provider LiteLLM client, prompts, and hybrid memory."""

from aqp.llm.memory import BM25Memory, HybridMemory, MemoryEntry
from aqp.llm.ollama_client import (
    LLMResult,
    check_health,
    complete,
    deep_llm,
    get_crewai_llm,
    list_local_models,
    quick_llm,
)
from aqp.llm.providers import (
    LLMProvider,
    ProviderSpec,
    get_provider,
    list_providers,
    resolve_model,
    router_complete,
)
from aqp.llm.tokens import CATALOG as PRICE_CATALOG
from aqp.llm.tokens import PricePer1K, compute_cost, price_for

__all__ = [
    "BM25Memory",
    "HybridMemory",
    "LLMProvider",
    "LLMResult",
    "MemoryEntry",
    "PricePer1K",
    "PRICE_CATALOG",
    "ProviderSpec",
    "check_health",
    "complete",
    "compute_cost",
    "deep_llm",
    "get_crewai_llm",
    "get_provider",
    "list_local_models",
    "list_providers",
    "price_for",
    "quick_llm",
    "resolve_model",
    "router_complete",
]
