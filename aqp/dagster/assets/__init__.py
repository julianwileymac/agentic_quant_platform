"""Dagster assets exposed by the AQP code location."""
from __future__ import annotations

from aqp.dagster.alphavantage_intraday import ALPHAVANTAGE_INTRADAY_ASSETS
from aqp.dagster.assets.airbyte import AIRBYTE_ASSETS
from aqp.dagster.assets.catalog import CATALOG_ASSETS
from aqp.dagster.assets.compaction import COMPACTION_ASSETS
from aqp.dagster.assets.entities import ENTITY_ASSETS
from aqp.dagster.assets.profiling import PROFILING_ASSETS
from aqp.dagster.assets.sources import SOURCE_ASSETS

ASSET_GROUPS = (
    ("sources", SOURCE_ASSETS),
    ("entities", ENTITY_ASSETS),
    ("catalog", CATALOG_ASSETS),
    ("profiling", PROFILING_ASSETS),
    ("compaction", COMPACTION_ASSETS),
    ("airbyte", AIRBYTE_ASSETS),
    ("alpha_vantage_intraday", ALPHAVANTAGE_INTRADAY_ASSETS),
)

ALL_ASSETS = [asset for _group_name, group_assets in ASSET_GROUPS for asset in group_assets]


def all_assets() -> list:
    """Return the deterministic AQP Dagster asset list."""
    return list(ALL_ASSETS)


__all__ = ["ALL_ASSETS", "ASSET_GROUPS", "all_assets"]
