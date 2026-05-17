"""Compute backend ABC.

A :class:`ComputeBackend` is an opaque handle to a computation engine
(local PyArrow, Dask, Ray) that knows how to:

- materialize an Arrow stream into a backend-native object
  (``from_arrow``);
- send a backend-native object back to Arrow (``to_arrow``);
- apply a partition-wise function (``map_partitions``);
- repartition a dataset (``repartition``).

The engine kernel never assumes the native object type — nodes that
opt in to a backend pull it from :class:`NodeContext.backend` and
dispatch on ``isinstance``-like duck typing.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


class ComputeBackendUnavailableError(RuntimeError):
    """Raised when a backend's optional deps are not importable."""


class ComputeBackend:
    """Opaque compute backend handle."""

    name: str = "abstract"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> None:
        """Optional eager init; called on first use by the executor."""

    def shutdown(self) -> None:
        """Optional teardown; called by the executor at end of run."""

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def from_arrow(self, batches: Iterable[pa.RecordBatch]) -> Any:
        """Materialize an Arrow stream into a backend-native object."""
        raise NotImplementedError

    def to_arrow(self, native: Any) -> pa.Table:
        """Convert a backend-native object back into a single Arrow table."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def map_partitions(
        self,
        native: Any,
        fn: Callable[[Any], Any],
    ) -> Any:
        """Apply ``fn`` to each partition; default is single-partition."""
        return fn(native)

    def repartition(self, native: Any, npartitions: int) -> Any:
        """Repartition the native object into ``npartitions`` chunks."""
        return native

    # ------------------------------------------------------------------
    # Convenience: introspection for the UI / Dagster.
    # ------------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """Return a JSON-serializable summary."""
        return {"name": self.name}


__all__ = [
    "ComputeBackend",
    "ComputeBackendUnavailableError",
]
