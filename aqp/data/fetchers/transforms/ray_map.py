"""Distributed map_batches via Ray Data.

Lazily imports Ray Data; falls back to in-process pandas when the
optional dep is missing.
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, TransformNode
from aqp.data.engine.registry import register_node

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "transform.ray_map",
    description="Distributed map_batches via Ray Data.",
    tags=("ray",),
)
class RayMapTransform(TransformNode):
    """Apply a callable across batches via Ray Data.

    ``callable_path`` is dotted (``module.func``) and receives a pandas
    DataFrame, returning one. ``num_workers`` and ``batch_size`` are
    forwarded to ``Dataset.map_batches``.
    """

    def __init__(
        self,
        *,
        callable_path: str,
        kwargs: dict[str, Any] | None = None,
        num_workers: int = 1,
        batch_size: int = 4_096,
        **node_kwargs: Any,
    ) -> None:
        super().__init__(**node_kwargs)
        self.callable_path = callable_path
        self.callable_kwargs = dict(kwargs or {})
        self.num_workers = max(1, int(num_workers))
        self.batch_size = max(1, int(batch_size))

    def _resolve(self) -> Callable[..., Any]:
        module_path, fn_name = self.callable_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        fn = getattr(mod, fn_name, None)
        if not callable(fn):
            raise TypeError(f"ray_map: {self.callable_path!r} is not callable")
        return fn

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa

        materialized = list(batches)
        if not materialized:
            return

        fn = self._resolve()
        kwargs = self.callable_kwargs

        try:
            import ray
            from ray import data as ray_data
        except Exception:  # noqa: BLE001 - optional dep missing
            logger.info("ray_map: ray unavailable; falling back to pandas")
            for batch in materialized:
                df = batch.to_pandas()
                new_df = fn(df, **kwargs)
                if new_df is None or len(new_df) == 0:
                    continue
                tbl = pa.Table.from_pandas(new_df, preserve_index=False)
                yield from tbl.to_batches()
            return

        if not ray.is_initialized():
            try:
                ray.init(ignore_reinit_error=True)
            except Exception:  # noqa: BLE001
                logger.exception("ray_map: ray.init failed; falling back to pandas")
                for batch in materialized:
                    df = batch.to_pandas()
                    new_df = fn(df, **kwargs)
                    if new_df is None or len(new_df) == 0:
                        continue
                    tbl = pa.Table.from_pandas(new_df, preserve_index=False)
                    yield from tbl.to_batches()
                return

        table = pa.Table.from_batches(materialized)
        ds = ray_data.from_arrow(table)

        def _wrapped(df):  # type: ignore[no-untyped-def]
            return fn(df, **kwargs)

        ds = ds.map_batches(
            _wrapped,
            batch_format="pandas",
            batch_size=self.batch_size,
            concurrency=self.num_workers,
        )
        for block in ds.iter_batches(batch_format="pyarrow"):
            yield from block.to_batches()
