"""Dagster jobs (named asset selections) for the AQP code location."""
from __future__ import annotations

from dagster import AssetSelection, define_asset_job

from aqp.dagster.alphavantage_intraday import (
    ALPHAVANTAGE_INTRADAY_JOBS,
    alphavantage_intraday_delta_job,
)
from aqp.dagster.assets.feature_materializer import materialize_features
from aqp.dagster.partitions import daily_partitions


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

time_partitioned_sources_job = define_asset_job(
    name="time_partitioned_sources_job",
    selection=AssetSelection.assets("fred_observations", "sec_filings", "gdelt_events"),
    partitions_def=daily_partitions(start_date="2024-01-01"),
    description=(
        "Daily partitioned source refresh for time-windowed regulatory "
        "and macro assets."
    ),
)

alphavantage_intraday_partition_job = define_asset_job(
    name="alphavantage_intraday_partition_job",
    selection=AssetSelection.assets(
        "alphavantage_universe",
        "alphavantage_intraday_request_plan",
        "alphavantage_intraday_delta",
        "alphavantage_intraday_datahub_update",
    ),
    partitions_def=daily_partitions(start_date="2024-01-01"),
    description=(
        "Daily partitioned intraday load track for Alpha Vantage assets."
    ),
)


ALL_JOBS = [
    full_data_refresh_job,
    regulatory_refresh_job,
    entity_extraction_job,
    compaction_job,
    profiling_job,
    datahub_sync_job,
    time_partitioned_sources_job,
    alphavantage_intraday_partition_job,
    materialize_features,
    *ALPHAVANTAGE_INTRADAY_JOBS,
]


__all__ = [
    "ALL_JOBS",
    "alphavantage_intraday_delta_job",
    "alphavantage_intraday_partition_job",
    "compaction_job",
    "datahub_sync_job",
    "entity_extraction_job",
    "full_data_refresh_job",
    "materialize_features",
    "profiling_job",
    "regulatory_refresh_job",
    "time_partitioned_sources_job",
]
