"""Dagster schedules for the AQP code location."""
from __future__ import annotations

from dagster import ScheduleDefinition, build_schedule_from_partitioned_job

from aqp.dagster.alphavantage_intraday import (
    ALPHAVANTAGE_INTRADAY_SCHEDULES,
    alphavantage_intraday_delta_schedule,
)
from aqp.dagster.jobs import (
    alphavantage_intraday_partition_job,
    compaction_job,
    datahub_sync_job,
    entity_extraction_job,
    full_data_refresh_job,
    profiling_job,
    regulatory_refresh_job,
    time_partitioned_sources_job,
)

# Daily at 02:00 UTC — full data refresh.
daily_full_refresh_schedule = ScheduleDefinition(
    name="daily_full_refresh",
    cron_schedule="0 2 * * *",
    job=full_data_refresh_job,
    execution_timezone="UTC",
    description="Daily full source refresh.",
)

# 04:00 UTC weekdays — regulatory refresh + entity extraction.
weekday_regulatory_schedule = ScheduleDefinition(
    name="weekday_regulatory_refresh",
    cron_schedule="0 4 * * 1-5",
    job=regulatory_refresh_job,
    execution_timezone="UTC",
)

# Hourly — push DataHub catalog state.
hourly_datahub_sync_schedule = ScheduleDefinition(
    name="hourly_datahub_sync",
    cron_schedule="15 * * * *",
    job=datahub_sync_job,
    execution_timezone="UTC",
)

# Every 6 hours — refresh profile cache for every Iceberg table.
six_hourly_profiling_schedule = ScheduleDefinition(
    name="six_hourly_profiling",
    cron_schedule="30 */6 * * *",
    job=profiling_job,
    execution_timezone="UTC",
)

# Sunday 05:00 UTC — Iceberg compaction.
weekly_compaction_schedule = ScheduleDefinition(
    name="weekly_compaction",
    cron_schedule="0 5 * * 0",
    job=compaction_job,
    execution_timezone="UTC",
)

# Daily at 06:00 UTC — entity LLM enrichment.
daily_entity_enrichment_schedule = ScheduleDefinition(
    name="daily_entity_enrichment",
    cron_schedule="0 6 * * *",
    job=entity_extraction_job,
    execution_timezone="UTC",
)

daily_time_partitioned_sources_schedule = build_schedule_from_partitioned_job(
    time_partitioned_sources_job,
    name="daily_time_partitioned_sources",
    minute_of_hour=10,
    hour_of_day=3,
)

daily_alphavantage_intraday_partition_schedule = build_schedule_from_partitioned_job(
    alphavantage_intraday_partition_job,
    name="daily_alphavantage_intraday_partition",
    minute_of_hour=40,
    hour_of_day=1,
)


ALL_SCHEDULES = [
    daily_full_refresh_schedule,
    weekday_regulatory_schedule,
    hourly_datahub_sync_schedule,
    six_hourly_profiling_schedule,
    weekly_compaction_schedule,
    daily_entity_enrichment_schedule,
    daily_time_partitioned_sources_schedule,
    daily_alphavantage_intraday_partition_schedule,
    *ALPHAVANTAGE_INTRADAY_SCHEDULES,
]


__all__ = [
    "ALL_SCHEDULES",
    "alphavantage_intraday_delta_schedule",
    "daily_entity_enrichment_schedule",
    "daily_alphavantage_intraday_partition_schedule",
    "daily_full_refresh_schedule",
    "daily_time_partitioned_sources_schedule",
    "hourly_datahub_sync_schedule",
    "six_hourly_profiling_schedule",
    "weekday_regulatory_schedule",
    "weekly_compaction_schedule",
]
