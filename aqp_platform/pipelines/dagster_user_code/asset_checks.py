"""Dagster asset checks for the in-repo pipelines code location.

Asset checks are lightweight data-quality contracts that Dagster runs after
each materialization.  Each check returns ``AssetCheckResult(passed=...)``
and is shown alongside the asset in the Dagster UI.

The checks here are intentionally generic so they exercise the framework
end-to-end without imposing strong assumptions on schemas - extend them per
asset as the data dictionary stabilises.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dagster import AssetCheckResult, AssetCheckSeverity, asset_check

from .datahub_assets import (
    datahub_api_sources,
    datahub_lakehouse_sources,
    datahub_mlflow_sources,
    datahub_platform_sources,
)


def _result_status(materialization_metadata: dict) -> str:
    """Pull the workflow status string out of the run metadata."""

    raw = materialization_metadata.get("status")
    if hasattr(raw, "value"):
        return str(raw.value)
    return str(raw or "")


def _build_workflow_check(asset_def, name: str):
    """Factory that returns a 'workflow succeeded' asset check for a DataHub asset."""

    @asset_check(
        asset=asset_def,
        name=name,
        description=(
            "Verifies the upstream Argo Workflow finished in `succeeded` state. "
            "Fails the check (severity=ERROR) when the workflow ended in any "
            "non-success state so the materialization is flagged in the UI."
        ),
    )
    def _check(context) -> AssetCheckResult:
        records = context.instance.get_latest_materialization_event(
            asset_def.key
        )
        if records is None:
            return AssetCheckResult(
                passed=False,
                severity=AssetCheckSeverity.WARN,
                description="No materialization event found yet",
            )
        meta = records.dagster_event.event_specific_data.materialization.metadata or {}
        status = _result_status(meta).lower()
        passed = status in {"succeeded", "completed"}
        return AssetCheckResult(
            passed=passed,
            severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
            description=f"Workflow status was {status!r}",
            metadata={"status": status},
        )

    return _check


datahub_lakehouse_workflow_succeeded = _build_workflow_check(
    datahub_lakehouse_sources, "datahub_lakehouse_workflow_succeeded"
)
datahub_mlflow_workflow_succeeded = _build_workflow_check(
    datahub_mlflow_sources, "datahub_mlflow_workflow_succeeded"
)
datahub_platform_workflow_succeeded = _build_workflow_check(
    datahub_platform_sources, "datahub_platform_workflow_succeeded"
)
datahub_api_workflow_succeeded = _build_workflow_check(
    datahub_api_sources, "datahub_api_workflow_succeeded"
)


@asset_check(
    asset=datahub_lakehouse_sources,
    name="datahub_lakehouse_freshness",
    description=(
        "Warn if the lakehouse DataHub ingestion has not materialized in the "
        "last 36 hours.  Daily schedule means anything older is suspicious."
    ),
)
def datahub_lakehouse_freshness(context) -> AssetCheckResult:
    record = context.instance.get_latest_materialization_event(
        datahub_lakehouse_sources.key
    )
    if record is None:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            description="Asset has never been materialized",
        )
    materialized_at = datetime.fromtimestamp(record.timestamp, tz=UTC)
    age = datetime.now(UTC) - materialized_at
    fresh = age < timedelta(hours=36)
    return AssetCheckResult(
        passed=fresh,
        severity=AssetCheckSeverity.WARN if not fresh else AssetCheckSeverity.WARN,
        description=f"Last materialization was {age} ago",
        metadata={"age_hours": age.total_seconds() / 3600.0},
    )


ALL_ASSET_CHECKS = [
    datahub_lakehouse_workflow_succeeded,
    datahub_mlflow_workflow_succeeded,
    datahub_platform_workflow_succeeded,
    datahub_api_workflow_succeeded,
    datahub_lakehouse_freshness,
]
