"""ML feature snapshot sink — Iceberg writer with recipe lineage tags.

Identical to :class:`IcebergSink` but stamps the resulting Iceberg
``meta`` with ``pipeline_recipe_id`` / ``dataset_version_id`` / a stable
``feature_snapshot_id`` so users can reload the exact preprocessed
features that fed a downstream training run. Routes every Iceberg call
through :func:`aqp.data.iceberg_catalog.append_arrow` per hard rule #3.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext, SinkNode
from aqp.data.engine.registry import register_node

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_node(
    "sink.ml_feature_snapshot",
    description=(
        "Append preprocessed feature batches to an Iceberg table with "
        "ML lineage tags (pipeline_recipe_id, dataset_version_id)."
    ),
    tags=("ml", "iceberg", "feature-store"),
)
class MlFeatureSnapshotSink(SinkNode):
    """Append Arrow batches to an Iceberg table with ML lineage stamps.

    Parameters
    ----------
    namespace, table:
        Iceberg identifier components.
    pipeline_recipe_id:
        Optional recipe id whose processors produced these features.
    dataset_version_id:
        Optional dataset version id the recipe was applied against.
    feature_snapshot_id:
        Optional explicit id (UUID generated otherwise). Returned in
        the result summary for downstream lineage rows.
    mode:
        ``append`` (default) or ``overwrite``.
    """

    def __init__(
        self,
        *,
        namespace: str,
        table: str,
        pipeline_recipe_id: str | None = None,
        dataset_version_id: str | None = None,
        feature_snapshot_id: str | None = None,
        mode: str = "append",
        tags: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not namespace or not table:
            raise ValueError("ml_feature_snapshot sink requires namespace and table")
        self.namespace = str(namespace)
        self.table = str(table)
        self.pipeline_recipe_id = pipeline_recipe_id
        self.dataset_version_id = dataset_version_id
        self.feature_snapshot_id = feature_snapshot_id or str(uuid.uuid4())
        self.mode = str(mode).lower()
        self.tags = list(tags or ["ml-features"])
        self.meta = dict(meta or {})

    @property
    def identifier(self) -> str:
        return f"{self.namespace}.{self.table}"

    def write(
        self,
        batches: Iterable[pa.RecordBatch],
        ctx: NodeContext,
    ) -> dict[str, Any]:
        from aqp.data.iceberg_catalog import (
            IcebergUnavailableError,
            append_arrow,
            create_or_replace_table,
            ensure_namespace,
        )

        ensure_namespace(self.namespace)

        accumulated_rows = 0
        first_batch = True
        for batch in batches:
            if batch.num_rows == 0:
                continue
            import pyarrow as pa

            table = pa.Table.from_batches([batch])
            try:
                if first_batch and self.mode == "overwrite":
                    create_or_replace_table(self.identifier, table.schema)
                    first_batch = False
                append_arrow(self.identifier, table)
            except IcebergUnavailableError as exc:
                logger.exception("ml_feature_snapshot iceberg unavailable: %s", exc)
                return {
                    "tables": [
                        {
                            "family": self.table,
                            "iceberg_identifier": self.identifier,
                            "rows_written": int(accumulated_rows),
                            "feature_snapshot_id": self.feature_snapshot_id,
                            "error": f"iceberg_unavailable: {exc}",
                        }
                    ],
                }
            accumulated_rows += int(batch.num_rows)
            first_batch = False

        ctx.emit(
            "sink",
            f"ml_feature_snapshot {self.identifier} rows={accumulated_rows} "
            f"snapshot={self.feature_snapshot_id}",
        )

        return {
            "tables": [
                {
                    "family": self.table,
                    "iceberg_identifier": self.identifier,
                    "rows_written": int(accumulated_rows),
                    "feature_snapshot_id": self.feature_snapshot_id,
                    "pipeline_recipe_id": self.pipeline_recipe_id,
                    "dataset_version_id": self.dataset_version_id,
                    "tags": list(self.tags),
                    "meta": dict(self.meta),
                }
            ],
        }


__all__ = ["MlFeatureSnapshotSink"]
