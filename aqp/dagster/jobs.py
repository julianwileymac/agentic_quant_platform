"""Dagster jobs (named asset selections) for the AQP code location."""
from __future__ import annotations

from dagster import AssetSelection, define_asset_job


full_data_refresh_job = define_asset_job(
    name="full_data_refresh_job",
    selection=AssetSelection.groups("aqp_sources"),
    description="Refresh every AQP source asset (regulatory, taxonomy, market).",
)

regulatory_refresh_job = define_asset_job(
    name="regulatory_refresh_job",
    selection=AssetSelection.assets(
        "cfpb_complaints",
        "fda_recalls",
        "uspto_patents",
        "sec_filings",
        "cfpb_entities",
        "fda_entities",
        "uspto_entities",
        "sec_entities",
    ),
    description="CFPB / FDA / USPTO / SEC + downstream entities.",
)

entity_extraction_job = define_asset_job(
    name="entity_extraction_job",
    selection=AssetSelection.groups("aqp_entities"),
    description="Run every entity extractor + LLM enrichment pass.",
)

compaction_job = define_asset_job(
    name="compaction_job",
    selection=AssetSelection.assets("iceberg_compaction"),
    description="Iceberg snapshot expiration + small-file rewrite.",
)

profiling_job = define_asset_job(
    name="profiling_job",
    selection=AssetSelection.assets("refresh_all_profiles"),
    description="Refresh dataset_profiles for every Iceberg table.",
)

datahub_sync_job = define_asset_job(
    name="datahub_sync_job",
    selection=AssetSelection.groups("aqp_catalog"),
    description="Push AQP catalog to DataHub + pull external state.",
)


# Keep the legacy AV intraday job alive so existing schedules continue working.
try:  # pragma: no cover - optional legacy path
    from aqp.dagster.alphavantage_intraday import alphavantage_intraday_delta_job
except Exception:  # noqa: BLE001
    alphavantage_intraday_delta_job = None  # type: ignore


ALL_JOBS = [
    full_data_refresh_job,
    regulatory_refresh_job,
    entity_extraction_job,
    compaction_job,
    profiling_job,
    datahub_sync_job,
]
if alphavantage_intraday_delta_job is not None:
    ALL_JOBS.append(alphavantage_intraday_delta_job)


__all__ = [
    "ALL_JOBS",
    "alphavantage_intraday_delta_job",
    "compaction_job",
    "datahub_sync_job",
    "entity_extraction_job",
    "full_data_refresh_job",
    "profiling_job",
    "regulatory_refresh_job",
]
