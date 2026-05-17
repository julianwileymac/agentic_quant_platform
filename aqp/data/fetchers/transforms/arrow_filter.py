"""Filter an Arrow stream by simple column predicates."""
from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, TransformNode
from aqp.data.engine.registry import register_node

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


_OPS = {"==", "!=", "<", "<=", ">", ">=", "in", "not_in", "is_null", "not_null"}


@register_node(
    "transform.arrow_filter",
    description="Filter an Arrow stream by per-column predicates.",
    tags=("arrow",),
)
class ArrowFilterTransform(TransformNode):
    """Filter rows using a list of ``{column, op, value}`` predicates.

    All predicates are AND-ed. Supported ops: ``==``, ``!=``, ``<``,
    ``<=``, ``>``, ``>=``, ``in``, ``not_in``, ``is_null``,
    ``not_null``. Falls back to a row-wise pandas filter when the
    pyarrow.compute path raises (e.g. unsupported types).
    """

    def __init__(
        self,
        *,
        predicates: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.predicates = list(predicates or [])
        for predicate in self.predicates:
            op = str(predicate.get("op") or "")
            if op not in _OPS:
                raise ValueError(f"arrow_filter: unsupported op {op!r}")

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        if not self.predicates:
            yield from batches
            return
        import pyarrow as pa
        import pyarrow.compute as pc

        for batch in batches:
            mask = None
            for predicate in self.predicates:
                column = str(predicate["column"])
                op = str(predicate["op"])
                if column not in batch.schema.names:
                    mask = pa.array([False] * batch.num_rows)
                    break
                col = batch[column]
                value = predicate.get("value")
                try:
                    sub = self._predicate_to_mask(pc, col, op, value)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "arrow_filter falling back to pandas: %s op=%s err=%s",
                        column,
                        op,
                        exc,
                    )
                    sub = self._fallback_mask(batch, column, op, value)
                mask = sub if mask is None else pc.and_(mask, sub)
            if mask is None:
                yield batch
                continue
            try:
                yield batch.filter(mask)
            except Exception:  # noqa: BLE001
                df = batch.to_pandas()
                df = df.loc[mask.to_pylist()]
                if len(df) == 0:
                    continue
                table = pa.Table.from_pandas(df, preserve_index=False)
                yield from table.to_batches()

    @staticmethod
    def _predicate_to_mask(pc, col, op: str, value: Any):  # type: ignore[no-untyped-def]
        if op == "==":
            return pc.equal(col, value)
        if op == "!=":
            return pc.not_equal(col, value)
        if op == "<":
            return pc.less(col, value)
        if op == "<=":
            return pc.less_equal(col, value)
        if op == ">":
            return pc.greater(col, value)
        if op == ">=":
            return pc.greater_equal(col, value)
        if op == "in":
            return pc.is_in(col, value_set=value)
        if op == "not_in":
            return pc.invert(pc.is_in(col, value_set=value))
        if op == "is_null":
            return pc.is_null(col)
        if op == "not_null":
            return pc.invert(pc.is_null(col))
        raise ValueError(f"unhandled op {op!r}")

    @staticmethod
    def _fallback_mask(batch, column: str, op: str, value: Any):  # type: ignore[no-untyped-def]
        import pyarrow as pa

        series = batch[column].to_pylist()
        if op == "==":
            return pa.array([s == value for s in series])
        if op == "!=":
            return pa.array([s != value for s in series])
        if op == "<":
            return pa.array([(s is not None and s < value) for s in series])
        if op == "<=":
            return pa.array([(s is not None and s <= value) for s in series])
        if op == ">":
            return pa.array([(s is not None and s > value) for s in series])
        if op == ">=":
            return pa.array([(s is not None and s >= value) for s in series])
        if op == "in":
            return pa.array([s in (value or []) for s in series])
        if op == "not_in":
            return pa.array([s not in (value or []) for s in series])
        if op == "is_null":
            return pa.array([s is None for s in series])
        if op == "not_null":
            return pa.array([s is not None for s in series])
        return pa.array([True] * batch.num_rows)
