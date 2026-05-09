"""Aggregate :class:`Definitions` for the AQP Dagster code location.

The cluster's ``pipelines-user-code`` Helm deployment loads this
module via ``dagster api grpc -m aqp.dagster.definitions``.
"""
from __future__ import annotations

from dagster import Definitions

from aqp.dagster.assets import all_assets
from aqp.dagster.checks import ALL_ASSET_CHECKS
from aqp.dagster.jobs import ALL_JOBS
from aqp.dagster.resources import build_resources
from aqp.dagster.schedules import ALL_SCHEDULES
from aqp.dagster.sensors import ALL_SENSORS

defs = Definitions(
    assets=all_assets(),
    asset_checks=ALL_ASSET_CHECKS,
    jobs=ALL_JOBS,
    schedules=ALL_SCHEDULES,
    sensors=ALL_SENSORS,
    resources=build_resources(),
)


__all__ = ["defs"]
