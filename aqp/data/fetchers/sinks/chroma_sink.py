"""Chroma metadata sink.

Indexes a small textual representation of each batch into a Chroma
collection so the dataset/code metadata search keeps working alongside
the new engine. Best-effort: a missing chromadb install logs and skips.
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
    "sink.chroma",
    description="Index batches into a Chroma collection (metadata search).",
    tags=("chroma",),
)
class ChromaSink(SinkNode):
    """Index batches as Chroma documents.

    ``id_column`` selects the column that becomes ``ids``.
    ``text_column`` selects the column whose values are embedded.
    Other columns become ``metadata`` automatically.
    """

    def __init__(
        self,
        *,
        collection: str,
        id_column: str,
        text_column: str,
        metadata_columns: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.collection = str(collection)
        self.id_column = str(id_column)
        self.text_column = str(text_column)
        self.metadata_columns = list(metadata_columns or [])

    def write(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> dict[str, Any]:
        try:
            from aqp.data.chroma_store import ChromaStore
        except Exception as exc:  # noqa: BLE001 - optional path
            logger.warning("ChromaSink unavailable (%s); skipping", exc)
            return {"rows_written": 0, "error": f"chroma_unavailable: {exc}"}

        store = ChromaStore()
        rows = 0
        for batch in batches:
            if batch.num_rows == 0:
                continue
            df = batch.to_pandas()
            if self.id_column not in df.columns or self.text_column not in df.columns:
                logger.debug(
                    "ChromaSink: skipping batch missing id/text columns"
                )
                continue
            ids = [str(v) for v in df[self.id_column].tolist()]
            texts = [str(v) for v in df[self.text_column].tolist()]
            metadatas = [
                {
                    c: (None if df[c].iloc[idx] is None else str(df[c].iloc[idx]))
                    for c in (self.metadata_columns or [])
                    if c in df.columns
                }
                for idx in range(len(df))
            ]
            try:
                store.upsert_documents(
                    collection=self.collection,
                    ids=ids,
                    documents=texts,
                    metadatas=metadatas,
                )
            except AttributeError:
                # Older ChromaStore exposes a single index_parquet_dir helper.
                logger.debug(
                    "ChromaStore.upsert_documents not present; skipping batch"
                )
            rows += len(ids)
        ctx.emit("sink", f"chroma indexed rows={rows}")
        return {
            "rows_written": rows,
            "tables": [
                {
                    "family": "chroma",
                    "iceberg_identifier": "",
                    "table_name": self.collection,
                    "rows_written": rows,
                }
            ],
        }
