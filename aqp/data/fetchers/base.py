"""Fetcher contract for the unified source library.

A :class:`Fetcher` is a thin wrapper around the work of producing
Arrow ``RecordBatch`` slices from one logical input source. Where the
existing :class:`aqp.data.engine.SourceNode` is the *engine-side* node
ABC, :class:`Fetcher` is the *source-author-side* convenience class:
subclass it once, get rate limiting + retries + pagination + lineage
recording for free, and become a registered ``source.*`` node.

Authors typically:

1. Subclass :class:`Fetcher` and override :meth:`fetch` (sync) or
   :meth:`afetch` (async).
2. Decorate the class with :func:`register_source_fetcher` (a thin
   wrapper over :func:`aqp.data.engine.register_node` that *also*
   upserts the ``data_sources`` row).
3. (Optional) override :meth:`probe` to run a cheap reachability check.
"""
from __future__ import annotations

import enum
import logging
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, SourceNode
from aqp.data.fabric.identity import FabricIdentity, FabricObjectMeta

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FetcherKind(str, enum.Enum):
    """Coarse fetcher kind discriminator surfaced to UI / DataHub."""

    API = "api"
    URL = "url"
    LOCAL = "local"
    STREAM = "stream"
    DATABASE = "database"
    CUSTOM = "custom"


class FetcherCapability(str, enum.Enum):
    """Capability flags that fetchers advertise."""

    SUPPORTS_PAGINATION = "supports_pagination"
    SUPPORTS_INCREMENTAL = "supports_incremental"
    SUPPORTS_PARALLELISM = "supports_parallelism"
    SUPPORTS_BACKFILL = "supports_backfill"
    SUPPORTS_RATE_LIMIT = "supports_rate_limit"
    REQUIRES_AUTH = "requires_auth"


# ---------------------------------------------------------------------------
# Helper dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RateLimit:
    """Token-bucket-ish throttle hint."""

    requests_per_minute: int | None = None
    requests_per_second: float | None = None
    burst: int = 1
    cooldown_seconds: float = 0.0
    daily_limit: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests_per_minute": self.requests_per_minute,
            "requests_per_second": self.requests_per_second,
            "burst": self.burst,
            "cooldown_seconds": self.cooldown_seconds,
            "daily_limit": self.daily_limit,
        }

    def sleep_for_call(self) -> float:
        """Return how long to sleep before the next call."""
        if self.requests_per_second:
            return max(0.0, 1.0 / float(self.requests_per_second))
        if self.requests_per_minute:
            return max(0.0, 60.0 / float(self.requests_per_minute))
        return 0.0


@dataclass
class RetryPolicy:
    """Linear / exponential retry knobs."""

    max_attempts: int = 5
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential: bool = True
    retry_on: tuple[type[BaseException], ...] = (Exception,)

    def delay_for(self, attempt: int) -> float:
        if attempt <= 1:
            return 0.0
        if self.exponential:
            delay = self.base_delay_seconds * (2 ** (attempt - 2))
        else:
            delay = self.base_delay_seconds
        return min(self.max_delay_seconds, delay)

    def should_retry(self, exc: BaseException) -> bool:
        return isinstance(exc, self.retry_on)


@dataclass
class Pagination:
    """Cursor / offset pagination configuration."""

    page_param: str | None = None
    cursor_param: str | None = None
    cursor_field: str | None = None
    page_size_param: str | None = None
    page_size: int | None = None
    next_link_field: str | None = None
    max_pages: int | None = None
    start_page: int = 1


@dataclass
class SourceLineage:
    """Lineage fragment emitted by a fetcher run."""

    source_name: str
    source_kind: FetcherKind = FetcherKind.API
    source_uri: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    rows_produced: int = 0
    bytes_received: int = 0
    requests: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> SourceLineage:
        if self.finished_at is None:
            self.finished_at = datetime.utcnow()
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_kind": self.source_kind.value,
            "source_uri": self.source_uri,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "rows_produced": int(self.rows_produced),
            "bytes_received": int(self.bytes_received),
            "requests": int(self.requests),
            "extras": dict(self.extras),
        }


@dataclass
class FetcherResult:
    """Aggregate result of a fetcher run.

    Wraps a Python iterator of Arrow batches so a fetcher can stream
    even when the result count is unknown ahead of time. The run-time
    is also tracked here for observability + lineage.
    """

    fetcher: str
    batches: Iterable[pa.RecordBatch]
    schema: pa.Schema | None = None
    lineage: SourceLineage | None = None
    extras: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fetcher base class — bridges into the engine's SourceNode
# ---------------------------------------------------------------------------


class Fetcher(SourceNode, FabricIdentity, metaclass=FabricObjectMeta):
    """Base class for every source-library fetcher.

    Subclasses override :meth:`fetch` (which must yield
    ``pyarrow.RecordBatch`` slices). The base class wires them up to:

    - the :class:`aqp.data.engine.SourceNode` interface so the engine
      executor can stream them,
    - rate limiting via :attr:`rate_limit`,
    - retry handling via :attr:`retry_policy`,
    - lineage recording via :class:`SourceLineage`.

    Most subclasses also set:

    - :attr:`provider_name` (the ``data_sources.name`` row),
    - :attr:`source_kind` (``api`` / ``url`` / ``local`` / ``stream``),
    - :attr:`capabilities` (a tuple of :class:`FetcherCapability`).
    """

    __abstract_fabric__ = True
    provider_name: str = "unknown"
    source_kind: FetcherKind = FetcherKind.CUSTOM
    capabilities: tuple[FetcherCapability, ...] = ()
    default_rate_limit: RateLimit | None = None
    default_retry: RetryPolicy = RetryPolicy()

    def __init__(
        self,
        *,
        rate_limit: RateLimit | None = None,
        retry_policy: RetryPolicy | None = None,
        pagination: Pagination | None = None,
        chunk_rows: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.rate_limit = rate_limit or self.default_rate_limit
        self.retry_policy = retry_policy or self.default_retry
        self.pagination = pagination
        self.chunk_rows = chunk_rows
        self._lineage: SourceLineage | None = None
        self._last_call_at: float = 0.0

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        """Yield ``pyarrow.RecordBatch`` slices.

        Subclasses MUST override.
        """
        raise NotImplementedError

    def probe(self) -> dict[str, Any]:
        """Cheap reachability check. Default returns ``{"ok": True}``."""
        return {"ok": True}

    def describe_capabilities(self) -> list[str]:
        return [c.value for c in self.capabilities]

    def source_uri(self) -> str | None:
        """Return the canonical URI / handle for this fetcher invocation."""
        return None

    # ------------------------------------------------------------------
    # SourceNode shim
    # ------------------------------------------------------------------

    def open(self, ctx: NodeContext) -> None:
        self._lineage = SourceLineage(
            source_name=self.provider_name,
            source_kind=self.source_kind,
            source_uri=self.source_uri(),
        )

    def stream(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        if self._lineage is None:
            self.open(ctx)
        assert self._lineage is not None
        for batch in self._invoke_fetch(ctx):
            try:
                self._lineage.rows_produced += int(batch.num_rows)
                self._lineage.bytes_received += int(batch.nbytes)
            except Exception:  # noqa: BLE001
                pass
            yield batch

    def close(self, ctx: NodeContext) -> None:
        if self._lineage is not None:
            self._lineage.finalize()
            ctx.lineage.setdefault("source_runs", []).append(self._lineage.to_dict())

    # ------------------------------------------------------------------
    # Internals: rate limit + retry
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        if self.rate_limit is None:
            return
        delay = self.rate_limit.sleep_for_call()
        if delay <= 0:
            return
        elapsed = time.perf_counter() - self._last_call_at
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_call_at = time.perf_counter()

    def _invoke_fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        attempt = 0
        last_exc: BaseException | None = None
        while attempt < max(1, self.retry_policy.max_attempts):
            attempt += 1
            try:
                self._throttle()
                yield from self.fetch(ctx)
                return
            except StopIteration:
                return
            except Exception as exc:  # noqa: BLE001 - retry surface
                last_exc = exc
                if not self.retry_policy.should_retry(exc):
                    raise
                wait = self.retry_policy.delay_for(attempt)
                logger.warning(
                    "fetcher %s failed attempt %d/%d (%s); retrying in %.2fs",
                    self.provider_name,
                    attempt,
                    self.retry_policy.max_attempts,
                    exc,
                    wait,
                )
                if wait > 0:
                    time.sleep(wait)
        if last_exc is not None:
            raise last_exc

    # ------------------------------------------------------------------
    # Convenience: turn a list of batches into a stream
    # ------------------------------------------------------------------

    @staticmethod
    def from_arrow_batches(batches: Iterable[pa.RecordBatch]) -> Iterator[pa.RecordBatch]:
        for batch in batches:
            yield batch

    @staticmethod
    def from_pandas(df: Any, *, chunk_rows: int = 50_000) -> Iterator[pa.RecordBatch]:
        """Yield Arrow batches by chunking a pandas DataFrame."""
        import pyarrow as pa

        if df is None or len(df) == 0:
            return
        table = pa.Table.from_pandas(df, preserve_index=False)
        for start in range(0, table.num_rows, chunk_rows):
            yield from table.slice(start, chunk_rows).to_batches()


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def register_source_fetcher(
    name: str,
    *,
    display_name: str | None = None,
    kind: FetcherKind = FetcherKind.API,
    description: str | None = None,
    base_url: str | None = None,
    auth_type: str = "none",
    credentials_ref: str | None = None,
    rate_limit: RateLimit | None = None,
    capabilities: tuple[str, ...] = (),
    domains: tuple[str, ...] = (),
    enabled: bool = True,
    tags: tuple[str, ...] = (),
    upsert_source_row: bool = True,
) -> Callable[[type], type]:
    """Decorator: register a Fetcher with the engine + ``data_sources``.

    ``name`` is the engine alias (e.g. ``source.alpha_vantage``). The
    function ALSO triggers an ``upsert_data_source`` call so the
    ``data_sources`` table self-populates with the fetcher's metadata
    on first import. The DB upsert is best-effort: a missing schema
    or DB connection logs at DEBUG and is skipped.
    """
    from aqp.data.engine import register_node
    from aqp.data.engine.nodes import NodeKind

    canonical_provider = name.split(".", 1)[-1] if "." in name else name

    def _wrap(cls: type) -> type:
        if not issubclass(cls, Fetcher):
            raise TypeError(f"register_source_fetcher: {cls!r} is not a Fetcher subclass")

        cls.provider_name = canonical_provider  # type: ignore[attr-defined]
        cls.source_kind = kind  # type: ignore[attr-defined]
        if rate_limit is not None:
            cls.default_rate_limit = rate_limit  # type: ignore[attr-defined]

        register_node(
            name,
            kind=NodeKind.SOURCE,
            description=description or (cls.__doc__ or "").strip().splitlines()[0]
            if (description or cls.__doc__)
            else "",
            tags=tags,
        )(cls)

        if upsert_source_row:
            try:
                from aqp.data.sources.registry import upsert_data_source

                upsert_data_source(
                    name=canonical_provider,
                    display_name=display_name or canonical_provider,
                    kind=kind.value,
                    base_url=base_url,
                    auth_type=auth_type,
                    capabilities={
                        "domains": list(domains),
                        "fetcher_alias": name,
                        "capabilities": list(capabilities),
                    },
                    rate_limits=rate_limit.to_dict() if rate_limit else None,
                    credentials_ref=credentials_ref,
                    enabled=enabled,
                )
            except Exception as exc:  # noqa: BLE001 - best-effort registration
                logger.debug(
                    "register_source_fetcher: upsert_data_source skipped for %s (%s)",
                    canonical_provider,
                    exc,
                )

        return cls

    return _wrap


__all__ = [
    "Fetcher",
    "FetcherCapability",
    "FetcherKind",
    "FetcherResult",
    "Pagination",
    "RateLimit",
    "RetryPolicy",
    "SourceLineage",
    "register_source_fetcher",
]
