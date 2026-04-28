"""Dagster ``ConfigurableResource`` instances shared across assets.

Each resource is a thin wrapper around an existing AQP component:

- :class:`AqpEngineResource` — entry point for running pipelines (used
  by data-engine assets that want to call ``Pipeline.from_manifest``).
- :class:`AqpIcebergResource` — wraps :func:`append_arrow` so assets
  don't import the catalog module directly.
- :class:`AqpDataHubResource` — wraps the DataHub emitter / puller.
- :class:`AqpComputeResource` — surfaces the chosen compute backend
  for an asset (Local / Dask / Ray).

The Dagster import is best-effort so importing this module without
Dagster installed (e.g. local API) is harmless.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


try:
    from dagster import ConfigurableResource
except Exception:  # noqa: BLE001 - optional dep
    ConfigurableResource = object  # type: ignore[misc, assignment]


class AqpEngineResource(ConfigurableResource):  # type: ignore[misc]
    """Run a :class:`aqp.data.engine.PipelineManifest` from a Dagster asset."""

    default_namespace: str = "aqp"

    def run_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        from aqp.data.engine import (
            Pipeline,
            PipelineManifest,
            build_executor,
        )

        spec = PipelineManifest.model_validate(manifest)
        pipeline = Pipeline.from_manifest(spec)
        executor = build_executor(spec)
        result = executor.execute(pipeline)
        return result.to_dict()


class AqpIcebergResource(ConfigurableResource):  # type: ignore[misc]
    """Convenience handle around :mod:`aqp.data.iceberg_catalog`."""

    default_namespace: str = "aqp"

    def append_arrow(self, identifier: str, table: Any) -> None:
        from aqp.data.iceberg_catalog import append_arrow, ensure_namespace

        namespace, _ = identifier.rsplit(".", 1)
        ensure_namespace(namespace)
        append_arrow(identifier, table)

    def list_namespaces(self) -> list[str]:
        from aqp.data.iceberg_catalog import list_namespaces

        return list(list_namespaces())


class AqpDataHubResource(ConfigurableResource):  # type: ignore[misc]
    """DataHub emitter facade for catalog assets."""

    enabled: bool = False

    def emit_dataset(self, *, urn: str, payload: dict[str, Any]) -> dict[str, Any]:
        from aqp.config import settings

        if not (self.enabled or settings.datahub_sync_enabled):
            return {"emitted": False, "reason": "disabled"}
        try:
            from aqp.data.datahub import push_dataset

            return push_dataset(urn=urn, payload=payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AqpDataHubResource emit failed: %s", exc)
            return {"emitted": False, "error": str(exc)}


class AqpComputeResource(ConfigurableResource):  # type: ignore[misc]
    """Compute backend selector resource."""

    backend: str = "auto"

    def pick_backend(self, *, rows: int, bytes: int) -> dict[str, Any]:
        from aqp.data.compute.selection import SizeHint, pick_backend
        from aqp.data.engine.manifest import ComputeBackendKind

        spec = pick_backend(
            SizeHint(rows=int(rows), bytes=int(bytes)),
            requested=ComputeBackendKind(self.backend),
        )
        return spec.model_dump(mode="json")


class AqpAirbyteResource(ConfigurableResource):  # type: ignore[misc]
    """Airbyte client facade for Dagster assets and sensors."""

    enabled: bool = False

    def health(self) -> dict[str, Any]:
        from aqp.services.airbyte_client import AirbyteClient

        if not self.enabled:
            return {"ok": False, "reason": "disabled"}
        return AirbyteClient().health()

    def trigger_sync(self, connection_id: str) -> dict[str, Any]:
        from aqp.services.airbyte_client import AirbyteClient

        if not self.enabled:
            return {"queued": False, "reason": "disabled"}
        return AirbyteClient().trigger_sync(connection_id)


def build_resources() -> dict[str, Any]:
    """Bundle every resource into a ``Definitions(resources=...)`` dict."""
    from aqp.config import settings

    return {
        "engine": AqpEngineResource(),
        "iceberg": AqpIcebergResource(),
        "datahub": AqpDataHubResource(enabled=bool(settings.datahub_sync_enabled)),
        "compute": AqpComputeResource(backend=settings.compute_backend_default or "auto"),
        "airbyte": AqpAirbyteResource(enabled=bool(settings.airbyte_enabled)),
    }


__all__ = [
    "AqpComputeResource",
    "AqpAirbyteResource",
    "AqpDataHubResource",
    "AqpEngineResource",
    "AqpIcebergResource",
    "build_resources",
]
