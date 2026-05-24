"""LangGraph agent memory helpers backed by Redis 8 Stack.

Thin wrappers around `langgraph.checkpoint.redis.RedisSaver` and
`langgraph.store.redis.RedisStore` that use the shared
:class:`RedisSettings` from :mod:`pipelines.config`.

The module imports langgraph-checkpoint-redis lazily so pipelines that
don't need agent memory are not forced to install the dependency.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from .config import RedisSettings, get_redis_settings

logger = logging.getLogger(__name__)


_INSTALL_HINT = (
    "langgraph-checkpoint-redis is not installed. "
    "`pip install langgraph-checkpoint-redis>=0.4.0`."
)


def _require_langgraph() -> tuple[Any, Any, Any]:
    try:
        from langgraph.checkpoint.redis import RedisSaver  # type: ignore
        from langgraph.store.redis import RedisStore  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(_INSTALL_HINT) from exc

    try:  # Optional middleware exports (v0.4+).
        from langgraph.middleware.redis import (  # type: ignore
            SemanticCacheConfig,
            SemanticCacheMiddleware,
        )

        middleware = {
            "SemanticCacheConfig": SemanticCacheConfig,
            "SemanticCacheMiddleware": SemanticCacheMiddleware,
        }
    except Exception:  # pragma: no cover
        middleware = {}

    return RedisSaver, RedisStore, middleware


def get_checkpointer(
    settings: RedisSettings | None = None,
    *,
    setup: bool = True,
) -> Any:
    """Return a configured ``RedisSaver`` checkpointer.

    Call with ``setup=False`` if you know the RediSearch indexes already
    exist to avoid an extra round-trip.  The tutorial guidance ("call
    .setup() on first use") is honored by default.
    """
    saver_cls, _, _ = _require_langgraph()
    s = settings or get_redis_settings()
    saver = saver_cls.from_conn_string(s.dsn())
    if setup:
        try:
            saver.__enter__()  # type: ignore[attr-defined]
            saver.setup()
        except AttributeError:
            # Older versions returned the saver directly without a ctx mgr
            saver.setup()
    return saver


def get_store(
    *,
    vector_dims: int = 1536,
    distance: str = "cosine",
    text_fields: Iterable[str] = ("text",),
    default_ttl_seconds: int | None = 3600,
    settings: RedisSettings | None = None,
) -> Any:
    """Return a configured ``RedisStore`` for long-term agent memory.

    ``vector_dims`` should match the embedding model dimension (e.g.
    1536 for text-embedding-3-small, 768 for many open models, 16 for
    the deterministic fallback in :mod:`pipelines.vector_io`).
    """
    _, store_cls, _ = _require_langgraph()
    s = settings or get_redis_settings()

    index_config = {
        "dims": int(vector_dims),
        "distance_type": distance,
        "fields": list(text_fields),
    }
    ttl_config = None
    if default_ttl_seconds is not None:
        ttl_config = {
            "default_ttl": int(default_ttl_seconds),
            "refresh_on_read": True,
        }

    store = store_cls.from_conn_string(
        s.dsn(),
        index=index_config,
        ttl=ttl_config,
    )
    try:
        store.__enter__()  # type: ignore[attr-defined]
        store.setup()
    except AttributeError:
        store.setup()
    return store


def get_semantic_cache_middleware(
    *,
    name: str = "llm_cache",
    distance_threshold: float = 0.15,
    ttl_seconds: int = 3600,
    settings: RedisSettings | None = None,
) -> Any | None:
    """Return a ``SemanticCacheMiddleware`` if the langgraph extra is present.

    Returns ``None`` when the middleware is not available so callers can
    unconditionally do ``middleware = ... or []``.
    """
    _, _, middleware = _require_langgraph()
    if not middleware:
        return None
    s = settings or get_redis_settings()
    config = middleware["SemanticCacheConfig"](
        redis_url=s.dsn(),
        name=name,
        distance_threshold=distance_threshold,
        ttl_seconds=ttl_seconds,
    )
    return middleware["SemanticCacheMiddleware"](config)


def langgraph_available() -> bool:
    """Return True if langgraph-checkpoint-redis can be imported."""
    try:
        _require_langgraph()
        return True
    except Exception:  # pragma: no cover
        return False


__all__ = [
    "get_checkpointer",
    "get_semantic_cache_middleware",
    "get_store",
    "langgraph_available",
]
