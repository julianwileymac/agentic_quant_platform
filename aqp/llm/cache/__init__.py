"""Optional caching layer for the LLM router.

Two implementations:

- :class:`SemanticLLMCache` — vectorises the prompt + cosine-search a
  Redis index for high-similarity hits. Best for chat where users
  paraphrase the same question.
- (Future) ``ExactLLMCache`` — SHA256 of the messages -> response.
  Cheaper, less coverage.

Gated by :attr:`Settings.llm_semantic_cache_enabled` so the base
install (Ollama-only, no extras) keeps working without the cache.
"""
from __future__ import annotations

from aqp.llm.cache.semantic import SemanticLLMCache, get_semantic_cache

__all__ = ["SemanticLLMCache", "get_semantic_cache"]
