"""Node ABCs for the unified data engine.

Three node kinds compose every pipeline:

- :class:`SourceNode` produces an Arrow ``RecordBatch`` stream from
  scratch (HTTP API, file system, Kafka topic, etc.).
- :class:`TransformNode` consumes a stream and produces a derived stream
  (column projection, rename, filter, join, group-by).
- :class:`SinkNode` consumes a stream and emits a side effect (writes
  to Iceberg, Chroma, profile cache, Kafka, etc.).

Streams are :class:`collections.abc.Iterator` of ``pyarrow.RecordBatch``
to keep memory bounded. A node can also expose ``materialize`` /
``schema`` helpers when it cheaply knows the output shape ahead of time.

The engine itself is compute-backend-agnostic. Backends in
:mod:`aqp.data.compute` materialize the stream into native objects
(pandas, Dask DataFrame, Ray Data) when a node opts in via
``backend.from_arrow(stream)``.
"""
from __future__ import annotations

import enum
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

    from aqp.data.compute.backend import ComputeBackend


class NodeKind(str, enum.Enum):
    """Pipeline node kind discriminator."""

    SOURCE = "source"
    TRANSFORM = "transform"
    SINK = "sink"


@dataclass
class NodeContext:
    """Per-node runtime context handed to :meth:`Node.run`.

    Carries the compute backend, the manifest fragment that built the
    node, a progress callback, and shared bookkeeping that propagates
    across the pipeline (run id, started_at, lineage rows, etc.).
    """

    pipeline_id: str
    run_id: str
    node_name: str
    node_index: int
    backend: ComputeBackend | None = None
    progress_cb: Any = None
    chunk_rows: int = 50_000
    extras: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)

    def emit(self, stage: str, message: str, **extra: Any) -> None:
        """Forward a progress event to the registered callback (if any)."""
        if self.progress_cb is None:
            return
        try:
            self.progress_cb(stage, message, **extra)
        except TypeError:
            try:
                self.progress_cb(stage, message)
            except Exception:  # noqa: BLE001
                logger.debug("progress callback failed", exc_info=True)
        except Exception:  # noqa: BLE001
            logger.debug("progress callback failed", exc_info=True)


class Node:
    """Common base for every pipeline node."""

    kind: NodeKind = NodeKind.TRANSFORM
    """Class-level discriminator (overridden by subclasses)."""

    name: str | None = None

    def __init__(self, **kwargs: Any) -> None:
        # Capture spare kwargs so the manifest builder can pass arbitrary
        # JSON shape and we surface unknown keys via ``self.extra_kwargs``.
        self.extra_kwargs: dict[str, Any] = dict(kwargs)

    def describe(self) -> dict[str, Any]:
        """Return a JSON-friendly summary of the node's configuration."""
        return {
            "kind": self.kind.value,
            "name": self.name or self.__class__.__name__,
            "kwargs": dict(self.extra_kwargs),
        }


class SourceNode(Node):
    """Producer node — yields ``pyarrow.RecordBatch`` slices."""

    kind = NodeKind.SOURCE

    def open(self, ctx: NodeContext) -> None:
        """Optional resource setup (open API session, mount FS, etc.)."""

    def schema(self) -> pa.Schema | None:
        """Return the static schema if known ahead of execution."""
        return None

    def stream(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        """Yield one Arrow ``RecordBatch`` at a time."""
        raise NotImplementedError

    def close(self, ctx: NodeContext) -> None:
        """Optional resource teardown."""


class TransformNode(Node):
    """Stream->stream node — wraps an iterator with derived batches."""

    kind = NodeKind.TRANSFORM

    def open(self, ctx: NodeContext) -> None:
        """Optional resource setup."""

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        """Wrap an upstream iterator and yield transformed batches."""
        raise NotImplementedError

    def close(self, ctx: NodeContext) -> None:
        """Optional resource teardown."""


class SinkNode(Node):
    """Terminal node — consumes the stream and emits a side effect."""

    kind = NodeKind.SINK

    def open(self, ctx: NodeContext) -> None:
        """Optional resource setup."""

    def write(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> dict[str, Any]:
        """Persist every batch and return a result summary."""
        raise NotImplementedError

    def close(self, ctx: NodeContext) -> None:
        """Optional resource teardown."""


__all__ = [
    "Node",
    "NodeContext",
    "NodeKind",
    "SinkNode",
    "SourceNode",
    "TransformNode",
]
