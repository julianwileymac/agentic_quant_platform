"""Rename columns in an Arrow stream."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, TransformNode
from aqp.data.engine.registry import register_node

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "transform.arrow_rename",
    description="Rename columns in an Arrow stream via a mapping.",
    tags=("arrow",),
)
class ArrowRenameTransform(TransformNode):
    """Rename columns based on the ``mapping`` ``{old: new}`` dict."""

    def __init__(
        self,
        *,
        mapping: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.mapping = dict(mapping or {})

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        if not self.mapping:
            yield from batches
            return
        for batch in batches:
            new_names = [self.mapping.get(name, name) for name in batch.schema.names]
            yield batch.rename_columns(new_names)
