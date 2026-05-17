"""Single-process compute backend (PyArrow)."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from aqp.data.compute.backend import ComputeBackend

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


class LocalBackend(ComputeBackend):
    """Default backend: keep everything in-process via PyArrow tables.

    ``from_arrow`` materializes the upstream stream into a single
    :class:`pa.Table` because most local-mode nodes downstream want a
    table; the engine itself does *not* call ``from_arrow`` — it pipes
    record batches end-to-end.
    """

    name = "local"

    def __init__(self) -> None:
        super().__init__()
        self._started = False

    def startup(self) -> None:
        self._started = True

    def shutdown(self) -> None:
        self._started = False

    def from_arrow(self, batches: Iterable[pa.RecordBatch]) -> pa.Table:
        import pyarrow as pa

        materialized = list(batches)
        if not materialized:
            return pa.table({})
        return pa.Table.from_batches(materialized)

    def to_arrow(self, native: pa.Table) -> pa.Table:
        return native

    def map_partitions(
        self,
        native: pa.Table,
        fn: Callable[[pa.Table], pa.Table],
    ) -> pa.Table:
        return fn(native)

    def repartition(self, native: pa.Table, npartitions: int) -> pa.Table:
        # Single-process; partitioning is a no-op.
        return native

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "started": self._started}


__all__ = ["LocalBackend"]
