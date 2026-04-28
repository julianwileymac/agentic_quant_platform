"""Dagster schedules for the AQP code location."""
from __future__ import annotations

from dagster import ScheduleDefinition

from aqp.dagster.jobs import (
    compaction_job,
    datahub_sync_job,
    entity_extraction_job,
    full_data_refresh_job,
    profiling_job,
    regulatory_refresh_job,
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


ALL_SCHEDULES = [
    daily_full_refresh_schedule,
    weekday_regulatory_schedule,
    hourly_datahub_sync_schedule,
    six_hourly_profiling_schedule,
    weekly_compaction_schedule,
    daily_entity_enrichment_schedule,
]


# Re-export legacy AV intraday schedule when available.
try:  # pragma: no cover - optional legacy path
    from aqp.dagster.alphavantage_intraday import (
        alphavantage_intraday_delta_schedule,
    )

    ALL_SCHEDULES.append(alphavantage_intraday_delta_schedule)
except Exception:  # noqa: BLE001
    pass


__all__ = [
    "ALL_SCHEDULES",
    "daily_entity_enrichment_schedule",
    "daily_full_refresh_schedule",
    "hourly_datahub_sync_schedule",
    "six_hourly_profiling_schedule",
    "weekday_regulatory_schedule",
    "weekly_compaction_schedule",
]
