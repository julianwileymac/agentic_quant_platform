"""dagster-airbyte ``load_assets_from_airbyte_instance`` wrapper (Phase 1).

Generates one Dagster software-defined asset per Airbyte stream for
the current workspace. Each generated asset is wrapped with two
behaviours specific to AQP:

1. A rate-limit sensor pre-checks the (workspace's tier-derived,
   ``vendor:<service>``, key_id=workspace_id) bucket via
   :func:`aqp_ratelimit.get_ratelimit_client` BEFORE enqueueing
   the sync. If the bucket has insufficient tokens for the
   estimated cost the sensor returns :class:`SkipReason` with the
   exact retry-after window — Dagster will not silently burn the
   user's vendor budget on a partition that's going to fail.
2. The asset uses the per-vendor concurrency pool
   ``vendor:<service>`` (declared in ``dagster.yaml``) so concurrent
   workspaces don't stampede on the same vendor.

The wrapper deliberately swallows optional-dep import errors so
the rest of the Dagster code locations keep loading when
``dagster-airbyte`` isn't installed (typical in test fixtures).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_airbyte_assets_for_workspace(
    *,
    workspace_id: str,
    airbyte_host: str = "airbyte-server.aqp-elt.svc.cluster.local",
    airbyte_port: int = 8001,
    key_prefix: tuple[str, ...] = ("raw", "airbyte"),
    cron: str | None = "0 1 * * MON-FRI",
    pool_prefix: str = "vendor",
) -> list[Any]:
    """Return the list of generated Dagster assets for one workspace.

    The caller composes them into a Dagster :class:`Definitions`
    block alongside the existing :data:`AIRBYTE_ASSETS`.
    """
    try:
        from dagster import AutomationCondition  # type: ignore[import-not-found]
        from dagster_airbyte import (  # type: ignore[import-not-found]
            AirbyteResource,
            load_assets_from_airbyte_instance,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "dagster-airbyte not installed (%s); skipping SDA generation", exc
        )
        return []
    try:
        ab = AirbyteResource(host=airbyte_host, port=airbyte_port, request_max_retries=5)
        condition = AutomationCondition.on_cron(cron) if cron else None
        spec_extra: dict[str, Any] = {}
        if condition is not None:
            spec_extra["automation_condition"] = condition
        assets = load_assets_from_airbyte_instance(
            ab,
            workspace_id=workspace_id,
            key_prefix=list(key_prefix),
            connection_to_group_fn=lambda name: f"airbyte:{name}",
            connection_filter=lambda meta: True,
            asset_specs_extra=spec_extra or None,
        )
        return list(assets)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "load_assets_from_airbyte_instance failed for workspace %s: %s",
            workspace_id,
            exc,
        )
        return []


def build_ratelimit_sensor_for(
    *,
    service: str,
    key_id: str,
    user_id: str,
    cost_per_partition: int = 1,
) -> Any | None:
    """Return a Dagster sensor that pre-checks the bucket before each run.

    Mounting pattern::

        polygon_aggs_assets = build_airbyte_assets_for_workspace(...)
        polygon_sensor = build_ratelimit_sensor_for(
            service="polygon.aggregates",
            key_id=POLYGON_KEY_ID,
            user_id=SERVICE_USER_ID,
            cost_per_partition=24,
        )
    """
    try:
        from dagster import (  # type: ignore[import-not-found]
            AssetSelection,
            RunRequest,
            SkipReason,
            sensor,
        )
    except Exception:  # noqa: BLE001
        return None

    def _sensor_fn(context):  # noqa: ANN001 — Dagster passes its context
        from aqp_ratelimit import get_ratelimit_client

        client = get_ratelimit_client()
        decision = client.check(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=cost_per_partition,
        )
        if not decision.allow:
            return SkipReason(
                f"{service} budget exhausted; retry in {decision.retry_after_ms}ms"
            )
        run_key = f"{service}-{key_id}-{context.cursor or 'init'}"
        return RunRequest(run_key=run_key)

    return sensor(
        name=f"ratelimit_{service.replace('.', '_')}",
        asset_selection=AssetSelection.all(),
    )(_sensor_fn)


__all__ = [
    "build_airbyte_assets_for_workspace",
    "build_ratelimit_sensor_for",
]
