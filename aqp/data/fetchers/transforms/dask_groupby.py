"""Distributed group-by aggregation via Dask DataFrame.

Lazily imports Dask: when the optional dep is missing the transform
falls back to an in-process pandas group-by so manifests stay
runnable on a minimal install.
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
    "transform.dask_groupby",
    description="Distributed group-by aggregation via Dask DataFrame.",
    tags=("dask", "aggregation"),
)
class DaskGroupByTransform(TransformNode):
    """Aggregate by ``by`` columns with the supplied ``aggs`` mapping.

    ``aggs`` accepts the pandas/Dask ``{column: agg_name}`` form
    (e.g. ``{"close": "mean", "volume": "sum"}``).
    """

    def __init__(
        self,
        *,
        by: list[str],
        aggs: dict[str, str],
        npartitions: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not by:
            raise ValueError("dask_groupby.by must be non-empty")
        self.by = list(by)
        self.aggs = dict(aggs or {})
        self.npartitions = npartitions

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa

        materialized = list(batches)
        if not materialized:
            return
        table = pa.Table.from_batches(materialized)
        df = table.to_pandas()

        try:
            import dask.dataframe as dd
        except Exception:  # noqa: BLE001 - optional dep missing
            logger.info("dask_groupby: dask unavailable; falling back to pandas")
            grouped = df.groupby(self.by, dropna=False).agg(self.aggs).reset_index()
        else:
            ddf = dd.from_pandas(
                df,
                npartitions=self.npartitions or max(1, len(df) // 250_000) or 1,
            )
            grouped = ddf.groupby(self.by, dropna=False).agg(self.aggs).reset_index()
            grouped = grouped.compute()

        if grouped is None or len(grouped) == 0:
            return
        result = pa.Table.from_pandas(grouped, preserve_index=False)
        yield from result.to_batches()
