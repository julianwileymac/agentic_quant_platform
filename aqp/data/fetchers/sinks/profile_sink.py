"""Profile sink — computes and caches column statistics.

Optional terminal node that consumes a stream, materializes a single
Arrow table, runs the profiler, and persists the result via
:func:`aqp.data.profiling.cache.write_profile`.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, SinkNode
from aqp.data.engine.registry import register_node

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "sink.profile",
    description="Compute Arrow column stats and cache them in Redis + Postgres.",
    tags=("profile",),
)
class ProfileSink(SinkNode):
    """Profile a stream and persist the result."""

    def __init__(
        self,
        *,
        namespace: str,
        name: str,
        version: int | None = None,
        engine: str = "auto",
        topk: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.namespace = str(namespace)
        self.name = str(name)
        self.version = version
        self.engine = str(engine)
        self.topk = topk

    def write(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> dict[str, Any]:
        import pyarrow as pa

        materialized = list(batches)
        if not materialized:
            return {"rows_written": 0, "tables": []}
        table = pa.Table.from_batches(materialized)

        try:
            from aqp.data.profiling import compute_profile, write_profile

            profile = compute_profile(table, engine=self.engine, topk=self.topk)
            write_profile(
                namespace=self.namespace,
                name=self.name,
                version=self.version,
                profile=profile,
            )
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.exception("profile sink failed: %s", exc)
            return {"rows_written": int(table.num_rows), "error": str(exc)}

        ctx.emit("sink", f"profile {self.namespace}.{self.name} columns={len(profile.get('columns', []))}")
        return {
            "rows_written": int(table.num_rows),
            "tables": [
                {
                    "family": self.name,
                    "iceberg_identifier": f"{self.namespace}.{self.name}",
                    "table_name": self.name,
                    "rows_written": int(table.num_rows),
                }
            ],
        }
