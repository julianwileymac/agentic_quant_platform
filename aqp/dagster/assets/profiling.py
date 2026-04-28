"""Profiling assets — refresh dataset_profiles cache for every dataset."""
from __future__ import annotations

from typing import Any

from dagster import AssetExecutionContext, asset


@asset(
    description="Refresh dataset profiles for every namespace.table.",
    group_name="aqp_profiling",
)
def refresh_all_profiles(context: AssetExecutionContext) -> dict[str, Any]:
    try:
        from aqp.data.iceberg_catalog import list_namespaces, list_tables
        from aqp.data.profiling import refresh_table_profile
    except Exception as exc:  # noqa: BLE001
        context.log.warning("profile refresh unavailable: %s", exc)
        return {"error": str(exc)}

    refreshed = 0
    errors: list[str] = []
    for namespace in list_namespaces():
        try:
            tables = list_tables(namespace)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"list_tables({namespace}): {exc}")
            continue
        for table in tables:
            name = table[-1] if isinstance(table, (list, tuple)) else str(table)
            try:
                refresh_table_profile(namespace, name)
                refreshed += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"profile {namespace}.{name}: {exc}")
    context.log.info("refreshed %d profiles", refreshed)
    return {"refreshed": refreshed, "errors": errors}


__all__ = ["refresh_all_profiles"]
