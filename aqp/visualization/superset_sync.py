"""Superset provisioning routines for AQP datasets."""
from __future__ import annotations

import json
import logging
from typing import Any

from aqp.data import iceberg_catalog
from aqp.observability import get_tracer
from aqp.services.superset_client import SupersetClient
from aqp.visualization.superset_assets import SupersetAssetPlan, build_asset_plan

logger = logging.getLogger(__name__)
_TRACER = get_tracer("aqp.visualization.superset_sync")


def discover_available_identifiers() -> list[str]:
    try:
        return iceberg_catalog.list_tables()
    except Exception:  # noqa: BLE001
        logger.info("Iceberg table discovery failed while planning Superset assets", exc_info=True)
        return []


def build_current_asset_plan() -> SupersetAssetPlan:
    return build_asset_plan(available_identifiers=discover_available_identifiers())


def sync_superset_assets(client: SupersetClient | None = None) -> dict[str, Any]:
    """Provision Trino database, datasets, charts, and a dashboard in Superset."""

    owns_client = client is None
    client = client or SupersetClient()
    try:
        with _TRACER.start_as_current_span("superset.sync_assets") as span:
            plan = build_current_asset_plan()
            span.set_attribute("superset.dataset_count", len(plan.datasets))
            span.set_attribute("superset.chart_count", len(plan.charts))
            span.set_attribute("superset.dashboard_count", len(plan.dashboards))

            database_id = _upsert_database(client, plan.database)
            dataset_ids: dict[str, int] = {}
            for dataset in plan.datasets:
                dataset_ids[dataset.identifier] = _upsert_dataset(
                    client,
                    database_id=database_id,
                    payload={
                        "database": database_id,
                        "schema": dataset.schema,
                        "table_name": dataset.table_name,
                        "owners": [],
                        "description": dataset.description,
                        "extra": json.dumps(
                            {"aqp": {"identifier": dataset.identifier, "tags": dataset.tags}}
                        ),
                    },
                )

            chart_ids: list[int] = []
            for chart in plan.charts:
                dataset_id = dataset_ids.get(chart.datasource_identifier)
                if not dataset_id:
                    continue
                chart_ids.append(
                    _upsert_chart(
                        client,
                        payload={
                            "slice_name": chart.slice_name,
                            "viz_type": chart.viz_type,
                            "datasource_id": dataset_id,
                            "datasource_type": "table",
                            "params": json.dumps(chart.params),
                        },
                    )
                )

            dashboard_ids: list[int] = []
            for dashboard in plan.dashboards:
                # Superset rejects unknown json_metadata keys, so AQP
                # bookkeeping (chart-id list) goes into the dashboard
                # response payload AQP returns, not into Superset itself.
                payload: dict[str, Any] = {
                    "dashboard_title": dashboard.dashboard_title,
                    "slug": dashboard.slug,
                    "json_metadata": json.dumps(dashboard.json_metadata),
                }
                if dashboard.position_json:
                    payload["position_json"] = json.dumps(dashboard.position_json)
                dashboard_ids.append(_upsert_dashboard(client, payload=payload))

            span.set_attribute("superset.upserted_datasets", len(dataset_ids))
            span.set_attribute("superset.upserted_charts", len(chart_ids))
            span.set_attribute("superset.upserted_dashboards", len(dashboard_ids))
            return {
                "database_id": database_id,
                "dataset_ids": dataset_ids,
                "chart_ids": chart_ids,
                "dashboard_ids": dashboard_ids,
                "planned": plan.to_dict(),
            }
    finally:
        if owns_client:
            client.close()


def _upsert_database(client: SupersetClient, payload: dict[str, Any]) -> int:
    existing = _first_matching(client.list_databases(), "database_name", payload["database_name"])
    if existing and existing.get("id") is not None:
        client.update_database(int(existing["id"]), payload)
        return int(existing["id"])
    response = client.create_database(payload)
    return _extract_id(response)


def _upsert_dataset(client: SupersetClient, *, database_id: int, payload: dict[str, Any]) -> int:
    for row in client.list_datasets():
        database = row.get("database") or {}
        row_database_id = database.get("id") if isinstance(database, dict) else row.get("database_id")
        if (
            row.get("schema") == payload["schema"]
            and row.get("table_name") == payload["table_name"]
            and int(row_database_id or -1) == int(database_id)
            and row.get("id") is not None
        ):
            client.update_dataset(int(row["id"]), payload)
            return int(row["id"])
    return _extract_id(client.create_dataset(payload))


def _upsert_chart(client: SupersetClient, payload: dict[str, Any]) -> int:
    existing = _first_matching(client.list_charts(), "slice_name", payload["slice_name"])
    if existing and existing.get("id") is not None:
        client.update_chart(int(existing["id"]), payload)
        return int(existing["id"])
    return _extract_id(client.create_chart(payload))


def _upsert_dashboard(client: SupersetClient, payload: dict[str, Any]) -> int:
    existing = _first_matching(client.list_dashboards(), "slug", payload["slug"])
    if existing and existing.get("id") is not None:
        client.update_dashboard(int(existing["id"]), payload)
        return int(existing["id"])
    return _extract_id(client.create_dashboard(payload))


def _first_matching(rows: list[dict[str, Any]], field: str, value: Any) -> dict[str, Any] | None:
    for row in rows:
        if row.get(field) == value:
            return row
    return None


def _extract_id(response: dict[str, Any]) -> int:
    """Pull the new row id out of a Superset POST response.

    Superset 4.x returns ``{"id": N, "result": {...}}`` where ``id`` lives
    at the top level. Older versions sometimes nested it inside
    ``result.id``. We check both spots before giving up.
    """

    if isinstance(response.get("id"), int):
        return int(response["id"])
    result = response.get("result")
    if isinstance(result, dict) and isinstance(result.get("id"), int):
        return int(result["id"])
    raise RuntimeError(f"Superset response did not include an id: {response!r}")
