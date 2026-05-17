"""Iceberg sink — writes Arrow batches into a managed Iceberg table.

Strictly delegates every Iceberg call to
:func:`aqp.data.iceberg_catalog.append_arrow` per the project's hard
rule #3. Records the new dataset version through
:func:`aqp.data.catalog.register_dataset_version` and refreshes the
profile cache.
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
    "sink.iceberg",
    description="Append Arrow batches to a managed Iceberg table.",
    tags=("iceberg",),
)
class IcebergSink(SinkNode):
    """Append Arrow batches to ``namespace.table`` via the wrapper.

    ``mode`` accepts:

    - ``append`` (default) — incremental append, table created on first call.
    - ``overwrite`` — drop + recreate before writing.
    """

    def __init__(
        self,
        *,
        namespace: str,
        table: str,
        mode: str = "append",
        provider: str = "engine",
        domain: str = "user.dataset",
        catalog_name: str | None = None,
        load_mode: str = "managed",
        source_uri: str | None = None,
        tags: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        refresh_profile: bool = True,
        compute_backend: str | None = None,
        dagster_asset_key: str | None = None,
        datahub_urn: str | None = None,
        code_version_sha: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not namespace or not table:
            raise ValueError("iceberg sink requires namespace and table")
        self.namespace = str(namespace)
        self.table = str(table)
        self.mode = str(mode).lower()
        self.provider = str(provider)
        self.domain = str(domain)
        self.catalog_name = catalog_name
        self.load_mode = str(load_mode)
        self.source_uri = source_uri
        self.tags = list(tags or [])
        self.meta = dict(meta or {})
        self.refresh_profile = bool(refresh_profile)
        self.compute_backend = compute_backend
        self.dagster_asset_key = dagster_asset_key
        self.datahub_urn = datahub_urn
        self.code_version_sha = code_version_sha

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
                logger.exception("iceberg append unavailable: %s", exc)
                return {
                    "tables": [
                        {
                            "family": self.table,
                            "iceberg_identifier": self.identifier,
                            "table_name": self.table,
                            "rows_written": int(accumulated_rows),
                            "error": f"iceberg_unavailable: {exc}",
                        }
                    ],
                }
            accumulated_rows += int(batch.num_rows)
            first_batch = False

        ctx.emit(
            "sink",
            f"iceberg append {self.identifier} rows={accumulated_rows}",
        )

        catalog_kwargs: dict[str, Any] = {}
        try:
            self._register_catalog(catalog_kwargs, ctx, accumulated_rows)
        except Exception:  # noqa: BLE001 - best-effort lineage
            logger.warning("iceberg sink: catalog registration skipped", exc_info=True)

        if self.refresh_profile and accumulated_rows > 0:
            try:
                self._refresh_profile(ctx)
            except Exception:  # noqa: BLE001 - best-effort
                logger.debug("iceberg sink: profile refresh skipped", exc_info=True)

        return {
            "tables": [
                {
                    "family": self.table,
                    "iceberg_identifier": self.identifier,
                    "table_name": self.table,
                    "rows_written": int(accumulated_rows),
                }
            ],
            "lineage": catalog_kwargs,
        }

    def _register_catalog(
        self,
        catalog_kwargs: dict[str, Any],
        ctx: NodeContext,
        rows: int,
    ) -> None:
        from aqp.data.catalog import register_dataset_version

        meta = {**self.meta, "engine_run_id": ctx.run_id}
        info = register_dataset_version(
            name=self.catalog_name or self.identifier,
            provider=self.provider,
            domain=self.domain,
            df=None,  # we don't materialize a pandas frame for big writes
            iceberg_identifier=self.identifier,
            load_mode=self.load_mode,
            source_uri=self.source_uri,
            tags=self.tags,
            meta=meta,
            engine_meta={
                "compute_backend": self.compute_backend,
                "dagster_asset_key": self.dagster_asset_key,
                "datahub_urn": self.datahub_urn,
                "code_version_sha": self.code_version_sha,
                "rows_written": rows,
            },
        )
        catalog_kwargs.update(info or {})

    def _refresh_profile(self, ctx: NodeContext) -> None:
        from aqp.data.profiling import refresh_table_profile

        refresh_table_profile(self.namespace, self.table)
