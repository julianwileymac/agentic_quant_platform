"""Smoke tests for the AQP-owned Dagster code location."""
from __future__ import annotations

import pytest


pytest.importorskip("dagster")


def test_aqp_definitions_include_alpha_vantage_and_checks():
    from aqp.dagster.assets import ALL_ASSETS, all_assets
    from aqp.dagster.checks import ALL_ASSET_CHECKS
    from aqp.dagster.definitions import defs
    from aqp.dagster.jobs import ALL_JOBS
    from aqp.dagster.schedules import ALL_SCHEDULES

    assert all_assets() == list(ALL_ASSETS)
    asset_keys = {asset.key.to_user_string() for asset in all_assets()}
    job_names = {job.name for job in ALL_JOBS}
    schedule_names = {schedule.name for schedule in ALL_SCHEDULES}
    check_names = {check.check_key.name for check in ALL_ASSET_CHECKS}

    assert defs is not None
    assert {
        "alphavantage_universe",
        "alphavantage_intraday_request_plan",
        "alphavantage_intraday_delta",
        "alphavantage_intraday_datahub_update",
    } <= asset_keys
    assert "alphavantage_intraday_delta_job" in job_names
    assert "time_partitioned_sources_job" in job_names
    assert "alphavantage_intraday_partition_job" in job_names
    assert "alphavantage_intraday_delta_schedule" in schedule_names
    assert "daily_time_partitioned_sources" in schedule_names
    assert "daily_alphavantage_intraday_partition" in schedule_names
    assert {
        "datahub_platform_instance_is_aqp",
        "datahub_external_platforms_exclude_assistants",
        "iceberg_namespace_configured",
    } <= check_names
