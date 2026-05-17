"""Parquet file sink — writes one parquet file per batch under ``output_dir``.

Useful for sandboxing and as a target for the legacy Parquet path.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, SinkNode
from aqp.data.engine.registry import register_node

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "sink.parquet",
    description="Write Arrow batches to a directory of Parquet files.",
    tags=("parquet", "filesystem"),
)
class ParquetSink(SinkNode):
    """Persist batches as ``output_dir/<prefix>-<idx>-<ts>.parquet``."""

    def __init__(
        self,
        *,
        output_dir: str | Path,
        prefix: str = "batch",
        compression: str = "zstd",
        single_file: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.output_dir = Path(output_dir)
        self.prefix = str(prefix)
        self.compression = str(compression)
        self.single_file = bool(single_file)

    def write(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> dict[str, Any]:
        import pyarrow as pa
        import pyarrow.parquet as pq

        self.output_dir.mkdir(parents=True, exist_ok=True)
        rows = 0
        files: list[str] = []
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")

        if self.single_file:
            collected = list(batches)
            if not collected:
                return {"rows_written": 0, "files": []}
            table = pa.Table.from_batches(collected)
            target = self.output_dir / f"{self.prefix}-{ts}.parquet"
            pq.write_table(table, target, compression=self.compression)
            return {
                "rows_written": int(table.num_rows),
                "files": [str(target)],
                "tables": [
                    {
                        "family": self.prefix,
                        "iceberg_identifier": "",
                        "table_name": self.prefix,
                        "rows_written": int(table.num_rows),
                    }
                ],
            }

        for idx, batch in enumerate(batches):
            if batch.num_rows == 0:
                continue
            table = pa.Table.from_batches([batch])
            target = self.output_dir / f"{self.prefix}-{idx:05d}-{ts}.parquet"
            pq.write_table(table, target, compression=self.compression)
            files.append(str(target))
            rows += int(batch.num_rows)
        ctx.emit("sink", f"parquet wrote {len(files)} file(s) rows={rows}")
        return {
            "rows_written": rows,
            "files": files,
            "tables": [
                {
                    "family": self.prefix,
                    "iceberg_identifier": "",
                    "table_name": self.prefix,
                    "rows_written": rows,
                    "files_consumed": len(files),
                }
            ],
        }
