"""AQP-owned Dagster asset checks for local configuration boundaries."""
from __future__ import annotations

from dagster import AssetCheckResult, AssetCheckSeverity, AssetKey, asset_check


@asset_check(
    asset=AssetKey("datahub_push_datasets"),
    description="Confirm DataHub emits under the AQP platform instance.",
)
def datahub_platform_instance_is_aqp() -> AssetCheckResult:
    from aqp.config import settings

    platform_instance = settings.datahub_platform_instance
    expected = "agentic-quant-platform"
    return AssetCheckResult(
        passed=platform_instance == expected,
        severity=AssetCheckSeverity.WARN,
        metadata={
            "platform_instance": platform_instance,
            "expected": expected,
        },
    )


@asset_check(
    asset=AssetKey("datahub_pull_external"),
    description="Confirm external DataHub pulls do not target assistant platform instances.",
)
def datahub_external_platforms_exclude_assistants() -> AssetCheckResult:
    from aqp.config import settings

    configured = settings.datahub_external_platforms
    normalized = configured.replace("_", "-").lower()
    passed = "agentic-assistants" not in normalized
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR,
        metadata={"datahub_external_platforms": configured},
    )


@asset_check(
    asset=AssetKey("iceberg_compaction"),
    description="Confirm the AQP Iceberg namespace is configured.",
)
def iceberg_namespace_configured() -> AssetCheckResult:
    from aqp.config import settings

    namespace = settings.iceberg_namespace_default
    return AssetCheckResult(
        passed=bool(namespace),
        severity=AssetCheckSeverity.ERROR,
        metadata={"iceberg_namespace_default": namespace},
    )


ALL_ASSET_CHECKS = [
    datahub_platform_instance_is_aqp,
    datahub_external_platforms_exclude_assistants,
    iceberg_namespace_configured,
]


__all__ = [
    "ALL_ASSET_CHECKS",
    "datahub_external_platforms_exclude_assistants",
    "datahub_platform_instance_is_aqp",
    "iceberg_namespace_configured",
]
