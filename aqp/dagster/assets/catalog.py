"""Catalog sync assets — push AQP datasets to DataHub, pull external state."""
from __future__ import annotations

from typing import Any

from dagster import asset

from aqp.dagster.resources import AqpDataHubResource


@asset(
    description="Push every AQP dataset_catalogs row to DataHub as a Dataset.",
    group_name="aqp_catalog",
    required_resource_keys={"datahub"},
)
def datahub_push_datasets(context) -> dict[str, Any]:
    datahub: AqpDataHubResource = context.resources.datahub

    try:
        from aqp.data.datahub import sync as datahub_sync
    except Exception as exc:  # noqa: BLE001
        context.log.warning("datahub sync unavailable: %s", exc)
        return {"emitted": 0, "error": str(exc)}

    summary = datahub_sync.push_all()
    context.log.info("datahub push summary: %s", summary)
    return summary


@asset(
    description="Pull external rpi/AQP catalog state from DataHub.",
    group_name="aqp_catalog",
    required_resource_keys={"datahub"},
)
def datahub_pull_external(context) -> dict[str, Any]:
    try:
        from aqp.data.datahub import sync as datahub_sync
    except Exception as exc:  # noqa: BLE001
        context.log.warning("datahub sync unavailable: %s", exc)
        return {"pulled": 0, "error": str(exc)}

    summary = datahub_sync.pull_external()
    context.log.info("datahub pull summary: %s", summary)
    return summary


CATALOG_ASSETS = [datahub_push_datasets, datahub_pull_external]


__all__ = ["CATALOG_ASSETS", "datahub_pull_external", "datahub_push_datasets"]
