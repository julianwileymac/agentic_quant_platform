"""Annotate batches with Iceberg-style partition columns.

Reading raw timestamps and emitting derived partition columns
(``date``, ``year_month``, ``vt_symbol_bucket``) lets the iceberg
sink keep partition specs stable while the upstream fetchers stay
oblivious to physical layout.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, TransformNode
from aqp.data.engine.registry import register_node

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "transform.iceberg_partition_strategy",
    description="Add partition columns (date, year_month, hash bucket) to a batch.",
    tags=("iceberg",),
)
class IcebergPartitionStrategyTransform(TransformNode):
    """Add Iceberg-friendly partition columns.

    ``timestamp_column`` (e.g. ``timestamp``) seeds ``date_column``,
    ``year_month_column``. ``bucket_column`` (e.g. ``vt_symbol``) seeds
    a hash-bucket column with ``num_buckets`` width.
    """

    def __init__(
        self,
        *,
        timestamp_column: str | None = None,
        date_column: str = "ds_date",
        year_month_column: str = "ds_year_month",
        bucket_column: str | None = None,
        bucket_output: str | None = None,
        num_buckets: int = 16,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.timestamp_column = timestamp_column
        self.date_column = date_column
        self.year_month_column = year_month_column
        self.bucket_column = bucket_column
        self.bucket_output = bucket_output or (
            f"{bucket_column}_bucket" if bucket_column else None
        )
        self.num_buckets = max(1, int(num_buckets))

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa
        import pyarrow.compute as pc

        for batch in batches:
            new_batch = batch
            if self.timestamp_column and self.timestamp_column in batch.schema.names:
                ts = batch.column(self.timestamp_column)
                try:
                    date_arr = pc.cast(pc.cast(ts, pa.date32()), pa.string())
                except Exception:  # noqa: BLE001
                    date_arr = pc.utf8_slice_codeunits(pc.cast(ts, pa.string()), 0, 10)
                ym_arr = pc.utf8_slice_codeunits(pc.cast(ts, pa.string()), 0, 7)
                new_batch = self._append_column(new_batch, self.date_column, date_arr)
                new_batch = self._append_column(new_batch, self.year_month_column, ym_arr)
            if self.bucket_column and self.bucket_output and self.bucket_column in batch.schema.names:
                col = batch.column(self.bucket_column).to_pylist()
                buckets = [
                    abs(hash(value or "")) % self.num_buckets for value in col
                ]
                new_batch = self._append_column(
                    new_batch,
                    self.bucket_output,
                    pa.array(buckets, type=pa.int32()),
                )
            yield new_batch

    @staticmethod
    def _append_column(batch: pa.RecordBatch, name: str, array: Any) -> pa.RecordBatch:
        import pyarrow as pa

        if name in batch.schema.names:
            idx = batch.schema.get_field_index(name)
            return batch.set_column(idx, name, array)
        return batch.append_column(name, array)
