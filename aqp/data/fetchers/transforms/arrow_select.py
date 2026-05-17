"""Project an Arrow stream to a subset of columns."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, TransformNode
from aqp.data.engine.registry import register_node

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "transform.arrow_select",
    description="Project an Arrow stream to a subset of columns.",
    tags=("arrow",),
)
class ArrowSelectTransform(TransformNode):
    """Project Arrow batches to ``columns``.

    Missing columns are dropped silently; required columns can be
    enforced via ``required=("a","b")`` (raises if missing).
    """

    def __init__(
        self,
        *,
        columns: list[str] | tuple[str, ...] | None = None,
        required: list[str] | tuple[str, ...] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.columns = list(columns or [])
        self.required = list(required or [])

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        for batch in batches:
            present = [c for c in self.columns if c in batch.schema.names]
            missing = [c for c in self.required if c not in batch.schema.names]
            if missing:
                raise ValueError(
                    f"arrow_select: required columns missing: {missing!r}"
                )
            if not self.columns:
                yield batch
                continue
            yield batch.select(present)
