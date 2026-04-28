"""Dagster assets for Alpha Vantage intraday planning and delta loads."""

from __future__ import annotations

from dagster import Definitions, ScheduleDefinition, asset, define_asset_job


@asset(description="Refresh the active Alpha Vantage instrument universe.")
def alphavantage_universe() -> dict:
    from aqp.data.sources.alpha_vantage.universe import AlphaVantageUniverseService

    service = AlphaVantageUniverseService()
    return service.sync_snapshot(state="active")


@asset(deps=[alphavantage_universe], description="Build reusable 1-minute intraday request components.")
def alphavantage_intraday_request_plan() -> dict:
    from aqp.data.sources.alpha_vantage.intraday_plan import build_intraday_plan

    return build_intraday_plan(symbols="all_active").to_dict()


@asset(deps=[alphavantage_intraday_request_plan], description="Load one configured batch of intraday components.")
def alphavantage_intraday_delta(alphavantage_intraday_request_plan: dict) -> dict:
    from aqp.data.sources.alpha_vantage.intraday_backfill import run_intraday_manifest

    result = run_intraday_manifest(
        manifest_path=alphavantage_intraday_request_plan["manifest_path"]
    )
    return result.to_dict()


@asset(deps=[alphavantage_intraday_delta], description="Confirm DataHub metadata emission for intraday data.")
def alphavantage_intraday_datahub_update(alphavantage_intraday_delta: dict) -> dict:
    from aqp.data.sources.alpha_vantage.datahub import emit_dataset_properties

    ok = emit_dataset_properties(
        platform="iceberg",
        name=alphavantage_intraday_delta["iceberg_identifier"],
        description="Alpha Vantage 1-minute intraday OHLCV data loaded by AQP",
        properties={
            "rows_written": alphavantage_intraday_delta.get("rows_written", 0),
            "manifest_path": alphavantage_intraday_delta.get("manifest_path", ""),
        },
    )
    return {"emitted": ok, "iceberg_identifier": alphavantage_intraday_delta["iceberg_identifier"]}


alphavantage_intraday_delta_job = define_asset_job(
    name="alphavantage_intraday_delta_job",
    selection=[
        alphavantage_universe,
        alphavantage_intraday_request_plan,
        alphavantage_intraday_delta,
        alphavantage_intraday_datahub_update,
    ],
)

alphavantage_intraday_delta_schedule = ScheduleDefinition(
    name="alphavantage_intraday_delta_schedule",
    cron_schedule="20 * * * *",
    job=alphavantage_intraday_delta_job,
)

defs = Definitions(
    assets=[
        alphavantage_universe,
        alphavantage_intraday_request_plan,
        alphavantage_intraday_delta,
        alphavantage_intraday_datahub_update,
    ],
    jobs=[alphavantage_intraday_delta_job],
    schedules=[alphavantage_intraday_delta_schedule],
)
