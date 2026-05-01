"""Zero-copy Arrow sharing across process boundaries.

The Phase 2 data-plane refactor pushes Arrow ``Table`` and ``RecordBatch``
objects between Celery workers, the FastAPI process, and the engine. The
default Celery JSON serializer would force every transfer through a
``Table.to_pylist()`` round-trip — orders of magnitude slower than the
underlying columnar in-memory format.

:class:`ZeroCopyManager` provides a uniform handle-based API:

- **In-process** (single Python interpreter): the table is held in a
  process-local dict (strong refs since handles are short-lived). No
  serialization happens; readers get the same Arrow buffers the writer
  built.
- **Cross-process** (Celery worker → API): the table is serialised once
  with the Arrow IPC stream format and stashed in Redis under
  ``aqp:zerocopy:{handle}``. The reader pulls it back with
  ``pa.ipc.open_stream`` which mmap-style decodes the columnar buffers
  without copying values.

The IPC stream payload preserves dtype, schema, and chunk layout —
unlike Parquet which re-encodes — so the round-trip cost is bounded by
the wire copy alone, not by deserialization.

Why not Plasma / Arrow Flight?
------------------------------

- Plasma was deprecated in pyarrow 10.x and removed in 13.x.
- Arrow Flight requires a long-running gRPC service plus a TLS story —
  too much surface for the local-first deployment.

Redis IPC streams give us a "good enough" zero-deserialization path with
the same Redis we already use for the Celery broker / progress bus.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any
from weakref import WeakValueDictionary

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    import pyarrow as pa  # noqa: F401


_REDIS_PREFIX = "aqp:zerocopy:"
_DEFAULT_TTL_SECONDS = 3600  # 1 hour — long enough for any single Celery task chain


class ZeroCopyManager:
    """Handle-based exchange of Arrow tables with optional Redis backing.

    Threading: the in-process registry uses a strong-ref dict because the
    handles are deliberately short-lived (release after the consumer
    completes). For long-lived caches use Iceberg + ``read_arrow`` instead.

    Parameters
    ----------
    redis_url
        Optional Redis URL. If omitted, the manager runs in single-process
        mode and ``share_arrow`` returns an in-memory handle. Cross-process
        ``fetch_arrow`` raises ``KeyError`` in this mode.
    ttl_seconds
        Default expiry for Redis-backed handles. Set to ``None`` to disable.
    namespace
        Prefix used for Redis keys (override for tests).
    """

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        ttl_seconds: int | None = _DEFAULT_TTL_SECONDS,
        namespace: str = _REDIS_PREFIX,
    ) -> None:
        self._registry: dict[str, Any] = {}
        # Track via WeakValueDict for stats only — strong refs in _registry
        # control lifetime, but this lets ``len(self._weak_view)`` reflect
        # what would survive if we relaxed the policy.
        self._weak_view: WeakValueDictionary[str, Any] = WeakValueDictionary()
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.namespace = namespace
        self._redis: Any = None  # lazy

    # ------------------------------------------------------------ helpers
    def _get_redis(self) -> Any | None:
        if self.redis_url is None:
            return None
        if self._redis is not None:
            return self._redis
        try:
            import redis  # type: ignore[import-not-found]

            self._redis = redis.Redis.from_url(self.redis_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ZeroCopyManager: redis unavailable (%s)", exc)
            self._redis = None
        return self._redis

    def _to_ipc_bytes(self, table: "pa.Table") -> bytes:
        import io

        import pyarrow as pa

        sink = io.BytesIO()
        with pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        return sink.getvalue()

    def _from_ipc_bytes(self, payload: bytes) -> "pa.Table":
        import io

        import pyarrow as pa

        with pa.ipc.open_stream(io.BytesIO(payload)) as reader:
            return reader.read_all()

    # ------------------------------------------------------------ writes
    def share_arrow(
        self,
        table: "pa.Table",
        *,
        cross_process: bool = False,
        handle: str | None = None,
    ) -> str:
        """Register ``table`` and return a handle.

        Parameters
        ----------
        table
            The :class:`pyarrow.Table` to share.
        cross_process
            When ``True`` the payload is also pushed to Redis as an Arrow
            IPC stream so a worker in another process can ``fetch_arrow``
            it. Single-process readers always hit the in-process registry
            first regardless of this flag.
        handle
            Optional explicit handle name (e.g. for deterministic tests).
            A random UUID is generated when omitted.
        """
        h = handle or f"zc-{uuid.uuid4().hex[:16]}"
        self._registry[h] = table
        try:
            self._weak_view[h] = table
        except TypeError:
            # WeakValueDictionary requires the value to be weak-referenceable.
            # pa.Table is, but defensive in case someone passes a wrapper.
            pass
        if cross_process:
            client = self._get_redis()
            if client is None:
                logger.debug(
                    "share_arrow(cross_process=True) requested but no redis backing — "
                    "handle %s will only resolve in-process",
                    h,
                )
            else:
                payload = self._to_ipc_bytes(table)
                key = f"{self.namespace}{h}"
                if self.ttl_seconds is not None:
                    client.set(key, payload, ex=int(self.ttl_seconds))
                else:
                    client.set(key, payload)
        return h

    def share_polars(
        self,
        df: Any,
        *,
        cross_process: bool = False,
        handle: str | None = None,
    ) -> str:
        """Convenience wrapper that converts a Polars DataFrame to Arrow first.

        Polars stores its data in Arrow buffers natively, so ``df.to_arrow()``
        is a zero-copy view in the common case.
        """
        return self.share_arrow(
            df.to_arrow(), cross_process=cross_process, handle=handle
        )

    # ------------------------------------------------------------- reads
    def fetch_arrow(self, handle: str) -> "pa.Table":
        """Resolve a handle to its :class:`pyarrow.Table`.

        Lookup order:

        1. In-process registry (zero-copy — same buffers as the writer).
        2. Redis IPC stream (single Redis hop + Arrow IPC decode).

        Raises ``KeyError`` if neither path resolves.
        """
        if handle in self._registry:
            return self._registry[handle]
        client = self._get_redis()
        if client is not None:
            key = f"{self.namespace}{handle}"
            payload = client.get(key)
            if payload is not None:
                tbl = self._from_ipc_bytes(payload)
                # Cache locally so repeat fetches are zero-copy.
                self._registry[handle] = tbl
                return tbl
        raise KeyError(f"unknown zero-copy handle: {handle!r}")

    def fetch_polars(self, handle: str):
        """Same as :meth:`fetch_arrow` but returns a Polars DataFrame."""
        import polars as pl

        return pl.from_arrow(self.fetch_arrow(handle))

    # ------------------------------------------------------- maintenance
    def release(self, handle: str) -> None:
        """Drop the in-process reference for ``handle``.

        Redis-backed payloads expire via TTL; this only frees process-local
        memory. Callers should release once the consumer has materialised
        whatever derived view it needs.
        """
        self._registry.pop(handle, None)

    def stats(self) -> dict[str, Any]:
        """Return diagnostic counts for monitoring / testing."""
        return {
            "in_process_handles": len(self._registry),
            "weak_view_handles": len(self._weak_view),
            "redis_backed": self._get_redis() is not None,
            "namespace": self.namespace,
            "ttl_seconds": self.ttl_seconds,
            "timestamp": time.time(),
        }


# Module-level singleton — Celery tasks and FastAPI routes share this.
# Configured lazily from ``settings.redis_url`` so importing the module
# doesn't open a Redis connection at module-load time.
_default_manager: ZeroCopyManager | None = None


def get_default_manager() -> ZeroCopyManager:
    """Return the process-wide default :class:`ZeroCopyManager`.

    Lazily binds to ``settings.redis_url`` for cross-process handles. Tests
    can override by monkey-patching ``aqp.core.memory._default_manager``.
    """
    global _default_manager
    if _default_manager is None:
        try:
            from aqp.config import settings

            _default_manager = ZeroCopyManager(redis_url=settings.redis_url)
        except Exception:
            _default_manager = ZeroCopyManager(redis_url=None)
    return _default_manager


__all__ = ["ZeroCopyManager", "get_default_manager"]
