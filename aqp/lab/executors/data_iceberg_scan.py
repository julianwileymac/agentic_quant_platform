"""``data.iceberg_scan`` — read a slice of an Iceberg table.

Routes through the canonical :func:`aqp.data.iceberg_catalog.read_arrow`
(AGENTS rule 3 — read side). Returns an output locator pointing at
the in-memory Arrow table for the next executor; nothing is persisted
back to Iceberg on the read path.

Params (validated by the registry's bundled JSON Schema in Phase 2):

- ``namespace`` (str, required) — Iceberg namespace.
- ``table`` (str, required) — table name within the namespace.
- ``columns`` (list[str] | None) — column projection.
- ``limit`` (int | None) — row limit; useful for previews.
- ``snapshot_id`` (str | None) — pin to a specific Iceberg snapshot;
  matched into ``read_arrow_at`` when set.

The executor records the resolved snapshot id on the output locator
so the reproducibility triple (content_hash, data_snapshot,
code_snapshot) on :class:`LabRun` stays honest.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    namespace = str(params.get("namespace") or "").strip()
    table = str(params.get("table") or "").strip()
    if not namespace or not table:
        return NodeResult(
            status="error",
            error="data.iceberg_scan requires non-empty 'namespace' and 'table'",
            log_label=f"iceberg_scan:{node.id}",
        )

    identifier = f"{namespace}.{table}"
    columns = params.get("columns")
    limit = params.get("limit")
    snapshot_id = params.get("snapshot_id")
    row_filter = params.get("row_filter")

    try:
        from aqp.data import iceberg_catalog
    except Exception as exc:  # noqa: BLE001
        logger.exception("Iceberg wrapper unavailable")
        return NodeResult(
            status="error",
            error=f"iceberg_catalog import failed: {exc}",
            log_label=f"iceberg_scan:{node.id}",
        )

    try:
        if snapshot_id:
            try:
                snapshot_int = int(snapshot_id)
            except (TypeError, ValueError):
                snapshot_int = None
            arrow_table = iceberg_catalog.read_arrow_at(
                identifier,
                snapshot_id=snapshot_int,
                columns=columns,
                limit=limit,
                row_filter=row_filter,
            )
        else:
            arrow_table = iceberg_catalog.read_arrow(
                identifier,
                columns=columns,
                limit=limit,
                row_filter=row_filter,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("iceberg read failed for %s", identifier)
        return NodeResult(
            status="error",
            error=f"iceberg read failed for {identifier!r}: {exc}",
            log_label=f"iceberg_scan:{node.id}",
        )

    if arrow_table is None:
        return NodeResult(
            status="error",
            error=f"iceberg table {identifier!r} not found",
            log_label=f"iceberg_scan:{node.id}",
        )

    n_rows = int(arrow_table.num_rows)
    n_cols = int(arrow_table.num_columns)

    locator: dict[str, Any] = {
        "kind": "iceberg",
        "identifier": identifier,
        "snapshot_id": snapshot_id,
        "columns": list(columns) if columns else None,
        "limit": limit,
        "rows": n_rows,
        "cols": n_cols,
    }

    # Stash the Arrow table on the context so in-process compilers
    # (EDA preview, single-process compose) can pick it up without an
    # extra round-trip through MinIO. Out-of-process Celery executors
    # don't inherit ``extras`` so they re-read from the locator.
    ctx.extras.setdefault("_arrow_outputs", {})[node.id] = arrow_table

    return NodeResult(
        status="done",
        output_locator=locator,
        metrics={"rows": n_rows, "cols": n_cols},
        log_label=f"iceberg_scan:{identifier} rows={n_rows}",
    )


__all__ = ["execute"]
