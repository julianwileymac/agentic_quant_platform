"""Iceberg compaction asset — expire snapshots, rewrite files."""
from __future__ import annotations

from typing import Any

from dagster import AssetExecutionContext, asset


@asset(
    description="Expire old Iceberg snapshots + rewrite small parquet files.",
    group_name="aqp_compaction",
)
def iceberg_compaction(context: AssetExecutionContext) -> dict[str, Any]:
    """Best-effort wrapper around the existing
    :mod:`aqp.data.iceberg_consolidate` helpers.
    """
    try:
        from aqp.data.iceberg_consolidate import consolidate_namespace
    except Exception as exc:  # noqa: BLE001
        context.log.warning("iceberg_consolidate unavailable: %s", exc)
        return {"error": str(exc)}

    try:
        from aqp.data.iceberg_catalog import list_namespaces
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    summary: dict[str, Any] = {}
    for namespace in list_namespaces():
        try:
            summary[namespace] = consolidate_namespace(namespace)
        except Exception as exc:  # noqa: BLE001
            context.log.warning("compaction failed for %s: %s", namespace, exc)
            summary[namespace] = {"error": str(exc)}
    return summary


__all__ = ["iceberg_compaction"]
