"""Semantic LLM completion cache backed by Redis vectors.

Stores ``(prompt_embedding, response)`` pairs under
``aqp:llm:semantic:*``. On lookup, embeds the new prompt and
cosine-searches; on a hit above
:attr:`Settings.llm_semantic_cache_threshold` (default 0.95) returns
the cached response instead of calling the foundational model.

Three failure modes — all of which silently fall through to the
underlying ``router_complete`` call:

1. ``redis-py`` is not installed.
2. Redis is unreachable.
3. The embeddings provider is not configured.

The cache is **disabled by default** so the base Ollama-only install
keeps working without any extras. Flip
``AQP_LLM_SEMANTIC_CACHE_ENABLED=true`` to opt in.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


_REDIS_PREFIX = "aqp:llm:semantic"
_INDEX_NAME = "aqp_llm_semantic_idx"


# ---------------------------------------------------------------------------
# Public dataclass (mirrors the bits of ``litellm.completion`` callers care about)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CachedCompletion:
    content: str
    role: str = "assistant"
    model: str = ""
    cached_at: float = 0.0
    similarity: float = 1.0

    def to_openai_shape(self) -> dict[str, Any]:
        """Re-shape into the dict ``router_complete`` returns."""
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": self.role, "content": self.content},
                    "finish_reason": "stop",
                }
            ],
            "model": self.model,
            "aqp_cache": {
                "hit": True,
                "similarity": self.similarity,
                "cached_at": self.cached_at,
            },
        }


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


def _embed_text(text: str) -> list[float] | None:
    """Embed *text* via the configured embeddings provider.

    Tries (in order):

    1. ``aqp.llm.embeddings.embed_text(text)`` — the platform helper if
       present.
    2. ``aqp.rag.embeddings.embed_query(text)`` — fallback to the RAG
       provider (already wired in production deploys).

    Returns ``None`` if no provider is reachable, in which case the
    semantic cache no-ops.
    """
    for module_name, fn_name in (
        ("aqp.llm.embeddings", "embed_text"),
        ("aqp.rag.embeddings", "embed_query"),
    ):
        try:
            mod = __import__(module_name, fromlist=[fn_name])
            fn = getattr(mod, fn_name, None)
            if fn is None:
                continue
            vec = fn(text)
            if isinstance(vec, list) and vec:
                return [float(v) for v in vec]
        except Exception:  # noqa: BLE001
            continue
    return None


def _cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    import math

    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list or len(a_list) != len(b_list):
        return 0.0
    dot = sum(x * y for x, y in zip(a_list, b_list))
    na = math.sqrt(sum(x * x for x in a_list))
    nb = math.sqrt(sum(y * y for y in b_list))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Cache class
# ---------------------------------------------------------------------------


class SemanticLLMCache:
    """Cosine-similarity cache for LLM completions over Redis.

    Single-flight protection lives in the caller (the L1 metadata
    cache pattern doesn't apply here because each prompt is unique
    enough that exact-key dedupe isn't useful). Concurrency-safe at
    the Redis level since all writes are HSET / SADD.
    """

    def __init__(
        self,
        *,
        threshold: float | None = None,
        ttl_seconds: int | None = None,
        max_entries: int | None = None,
    ) -> None:
        self.threshold = float(
            threshold
            if threshold is not None
            else getattr(settings, "llm_semantic_cache_threshold", 0.95)
        )
        self.ttl_seconds = int(
            ttl_seconds
            if ttl_seconds is not None
            else getattr(settings, "llm_semantic_cache_ttl_seconds", 3600)
        )
        self.max_entries = int(
            max_entries
            if max_entries is not None
            else getattr(settings, "llm_semantic_cache_max_entries", 10000)
        )
        self._client: Any | None = self._make_client()

    @property
    def enabled(self) -> bool:
        return bool(
            getattr(settings, "llm_semantic_cache_enabled", False)
        ) and self._client is not None

    # ------------------------------------------------- helpers
    def _make_client(self) -> Any | None:
        try:
            import redis  # type: ignore[import-not-found]
        except Exception:  # pragma: no cover
            return None
        url = (
            getattr(settings, "cache_redis_url", "")
            or getattr(settings, "redis_url", "")
        )
        if not url:
            return None
        try:
            client = redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            client.ping()
            return client
        except Exception:
            return None

    def _prompt_key(self, messages: list[dict[str, Any]]) -> str:
        flat = json.dumps(messages, default=str, sort_keys=True)
        return hashlib.sha256(flat.encode("utf-8")).hexdigest()[:32]

    def _index_key(self) -> str:
        return f"{_REDIS_PREFIX}:index"

    def _entry_key(self, prompt_hash: str) -> str:
        return f"{_REDIS_PREFIX}:entry:{prompt_hash}"

    @staticmethod
    def _last_user_text(messages: list[dict[str, Any]]) -> str:
        for msg in reversed(messages or []):
            if (msg.get("role") or "").lower() == "user":
                return str(msg.get("content") or "")
        # Fallback: last message of any role.
        if messages:
            return str(messages[-1].get("content") or "")
        return ""

    # ------------------------------------------------- public surface
    def lookup(
        self, messages: list[dict[str, Any]], model: str
    ) -> CachedCompletion | None:
        """Return a cached completion when one exists above the threshold."""
        if not self.enabled:
            return None
        prompt = self._last_user_text(messages)
        if not prompt:
            return None
        vec = _embed_text(prompt)
        if vec is None:
            return None
        try:
            members = self._client.smembers(self._index_key()) or set()
        except Exception:  # noqa: BLE001
            return None
        best: tuple[float, dict[str, Any]] | None = None
        for member in members:
            entry_raw = self._client.get(self._entry_key(str(member)))
            if not entry_raw:
                try:
                    self._client.srem(self._index_key(), member)
                except Exception:  # noqa: BLE001
                    pass
                continue
            try:
                entry = json.loads(entry_raw)
            except json.JSONDecodeError:
                continue
            if entry.get("model") != model:
                # Per-model isolation: a gpt-5 cache doesn't satisfy
                # a llama-3 call. Could be made router-aware in a
                # future revision.
                continue
            sim = _cosine_similarity(vec, entry.get("embedding") or [])
            if best is None or sim > best[0]:
                best = (sim, entry)
        if best is None or best[0] < self.threshold:
            return None
        sim, entry = best
        return CachedCompletion(
            content=str(entry.get("content") or ""),
            role=str(entry.get("role") or "assistant"),
            model=str(entry.get("model") or model),
            cached_at=float(entry.get("cached_at") or 0.0),
            similarity=float(sim),
        )

    def store(
        self,
        messages: list[dict[str, Any]],
        model: str,
        response: Any,
    ) -> None:
        """Store a completion. *response* is the dict shape returned by
        :func:`router_complete` (OpenAI-style ``{choices: [...], model: ...}``).
        """
        if not self.enabled:
            return
        prompt = self._last_user_text(messages)
        if not prompt:
            return
        content = ""
        try:
            content = str(response["choices"][0]["message"]["content"])
        except Exception:  # noqa: BLE001
            return
        if not content:
            return
        vec = _embed_text(prompt)
        if vec is None:
            return
        prompt_hash = self._prompt_key(messages)
        entry = {
            "model": model,
            "role": "assistant",
            "content": content,
            "embedding": vec,
            "cached_at": time.time(),
        }
        try:
            self._client.set(
                self._entry_key(prompt_hash),
                json.dumps(entry, default=str),
                ex=self.ttl_seconds,
            )
            self._client.sadd(self._index_key(), prompt_hash)
            # Cap index size — random eviction is fine here (we don't
            # need LRU semantics on the semantic cache).
            if self._client.scard(self._index_key()) > self.max_entries:
                for victim in self._client.srandmember(self._index_key(), 16) or []:
                    self._client.delete(self._entry_key(str(victim)))
                    self._client.srem(self._index_key(), victim)
        except Exception:  # noqa: BLE001
            logger.debug("semantic llm cache store failed", exc_info=True)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_CACHE: SemanticLLMCache | None = None


def get_semantic_cache() -> SemanticLLMCache:
    """Process-wide singleton; rebuilt on settings changes via test helpers."""
    global _CACHE
    if _CACHE is None:
        _CACHE = SemanticLLMCache()
    return _CACHE


def reset_semantic_cache_for_tests() -> None:
    global _CACHE
    _CACHE = None


__all__ = [
    "CachedCompletion",
    "SemanticLLMCache",
    "get_semantic_cache",
    "reset_semantic_cache_for_tests",
]
