"""Join an Arrow stream to a static lookup table."""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, TransformNode
from aqp.data.engine.registry import register_node

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "transform.arrow_join",
    description="Left-join an Arrow stream against a static lookup parquet/csv.",
    tags=("arrow",),
)
class ArrowJoinTransform(TransformNode):
    """Left-join the stream against a small static table.

    The lookup is loaded once on first batch (cheap parquet/csv read);
    every batch is then joined in-memory via PyArrow. Best for
    enriching with reference / dimension tables under ~1M rows.
    """

    def __init__(
        self,
        *,
        lookup_path: str | Path,
        on: str | list[str],
        how: str = "left outer",
        coalesce_keys: bool = True,
        select: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.lookup_path = Path(lookup_path)
        self.on = on if isinstance(on, list) else [on]
        self.how = str(how)
        self.coalesce_keys = bool(coalesce_keys)
        self.select = list(select) if select else None
        self._lookup: pa.Table | None = None

    def _load_lookup(self) -> pa.Table:
        if self._lookup is not None:
            return self._lookup
        import pyarrow as pa
        import pyarrow.csv as pa_csv
        import pyarrow.parquet as pa_parquet

        suffix = self.lookup_path.suffix.lower()
        if suffix in {".parquet", ".pq"}:
            self._lookup = pa_parquet.read_table(self.lookup_path)
        elif suffix in {".csv", ".tsv"}:
            self._lookup = pa_csv.read_csv(self.lookup_path)
        else:
            raise ValueError(f"arrow_join: unsupported lookup format {suffix!r}")
        if self.select:
            cols = [c for c in self.select if c in self._lookup.schema.names]
            self._lookup = self._lookup.select(cols)
        return self._lookup

    def transform(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa

        lookup = self._load_lookup()
        for batch in batches:
            left = pa.Table.from_batches([batch])
            joined = left.join(
                lookup,
                keys=self.on,
                join_type=self.how,
                coalesce_keys=self.coalesce_keys,
            )
            yield from joined.to_batches()
