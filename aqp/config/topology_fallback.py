"""Topology-driven fallback for URL-typed ``Settings`` fields.

Phase 0 of the AQP infra-expansion plan. Centralization rule
(plan section C.1):

    Resolution order: hardcoded default -> env (legacy ``AQP_*``) ->
    topology.yaml.

Pydantic-settings already implements the first two layers. This
module adds the third: when a URL field has not been set via
``AQP_*`` env (i.e. it's still at its hardcoded default) AND the
deployment topology declares an endpoint for the matching service,
the topology value wins.

The fallback is intentionally narrow:

- Only fields with ``URL_FALLBACK_FIELDS`` mapping entries are
  considered.
- The mapping is explicit per (Settings field, topology service id,
  endpoint name) so we never accidentally repoint settings to an
  unrelated topology entry.
- Setting any ``AQP_*`` env var on a covered field disables the
  fallback for that field (env always wins).
- A topology load failure logs a warning and leaves Settings
  untouched. Misbehaving topology files never break boot.

The frontend / control-plane side reads service URLs through the
``/manage/topology/services/{id}/endpoint`` route (the canonical
admin/control surface). AQP-side processes (Celery workers, FastAPI
app, CLI) call this fallback once at boot via
:func:`apply_topology_fallback`.
"""
from __future__ import annotations

import logging
from typing import Iterable, NamedTuple

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class _Mapping(NamedTuple):
    """Map a Settings field to a topology endpoint."""

    settings_field: str
    service_id: str
    endpoint_name: str


# Explicit mapping table. Each row says: when topology declares
# ``endpoints[<endpoint_name>]`` on the service whose ``id`` is
# ``<service_id>``, use that URL as the fallback for the matching
# ``Settings`` field. Anything not in this table is unaffected.
URL_FALLBACK_FIELDS: tuple[_Mapping, ...] = (
    # --- AQP-owned shared services (`aqp-*` namespaces in
    # `agentic_quant_platform/deployments/kubernetes/`).
    _Mapping("postgres_dsn", "postgres", "dsn"),
    _Mapping("postgres_async_dsn", "postgres", "async_dsn"),
    _Mapping("redis_url", "redis", "url"),
    _Mapping("redis_pubsub_url", "redis", "pubsub_url"),
    _Mapping("cache_redis_url", "redis", "cache_url"),
    _Mapping("minio_endpoint_url", "minio", "endpoint"),
    _Mapping("s3_endpoint_url", "minio", "endpoint"),
    _Mapping("kafka_bootstrap", "kafka", "bootstrap"),
    _Mapping("kafka_admin_bootstrap", "kafka", "admin_bootstrap"),
    _Mapping("schema_registry_url", "schema-registry", "ccompat"),
    _Mapping("kafka_admin_schema_registry_url", "schema-registry", "ccompat"),
    _Mapping("polaris_base_url", "polaris", "rest"),
    _Mapping("iceberg_rest_uri", "polaris", "iceberg_rest"),
    _Mapping("mlflow_tracking_uri", "mlflow", "tracking"),
    _Mapping("mlflow_registry_uri", "mlflow", "tracking"),
    _Mapping("dagster_webserver_url", "dagster", "webserver"),
    _Mapping("dagster_graphql_url", "dagster", "graphql"),
    _Mapping("airbyte_base_url", "airbyte", "ui"),
    _Mapping("airbyte_api_url", "airbyte", "api"),
    _Mapping("chroma_host", "chromadb", "host"),
    _Mapping("datahub_gms_url", "datahub", "gms"),
    _Mapping("flink_rest_url", "flink", "rest"),
    _Mapping("trino_uri", "trino", "uri"),
    _Mapping("trino_http_url", "trino", "http"),
    _Mapping("otel_endpoint", "otel-collector", "otlp_grpc"),
    _Mapping("cluster_mgmt_url", "aqp-cp", "manage"),
    _Mapping("aqp_api_url_internal", "aqp-core", "internal_api"),
    # --- Additive infra services. Added once their entries land in
    # topology.yaml; absent today, fallback is a no-op for these.
    _Mapping("redpanda_bootstrap", "redpanda", "bootstrap"),
    _Mapping("redpanda_admin_url", "redpanda", "admin"),
    _Mapping("redpanda_schema_registry_url", "redpanda", "schema_registry"),
    _Mapping("redpanda_connect_url", "redpanda-connect", "ui"),
    _Mapping("questdb_pg_url", "questdb", "pgwire"),
    _Mapping("questdb_ilp_url", "questdb", "ilp_tcp"),
    _Mapping("questdb_http_url", "questdb", "http"),
    _Mapping("phoenix_endpoint", "phoenix", "otlp_http"),
    _Mapping("phoenix_grpc_endpoint", "phoenix", "otlp_grpc"),
    _Mapping("phoenix_ui_url", "phoenix", "ui"),
    _Mapping("prometheus_url", "prometheus", "query"),
    _Mapping("prometheus_remote_write_url", "prometheus", "remote_write"),
    _Mapping("grafana_url", "grafana", "ui"),
    _Mapping("loki_url", "loki", "push"),
    _Mapping("tempo_otlp_url", "tempo", "otlp_grpc"),
    _Mapping("hudi_warehouse_url", "hudi", "warehouse"),
    _Mapping("hudi_metastore_url", "hudi", "metastore"),
)


def apply_topology_fallback(
    settings: BaseSettings,
    *,
    topology_path: str | None = None,
) -> dict[str, str]:
    """Mutate ``settings`` in place with topology fallback values.

    Returns a dict of ``{field_name: applied_url}`` for the fields that
    were updated. Empty dict means no changes.

    Safe to call repeatedly; the second call is a no-op (it skips any
    field that is no longer at its default).
    """
    try:
        from aqp_platform_core.topology import (
            TopologyLoadError,
            load_topology,
        )
    except Exception:  # noqa: BLE001
        logger.debug("aqp_platform_core.topology unavailable; skipping fallback")
        return {}

    try:
        topology = load_topology(topology_path)
    except TopologyLoadError as exc:
        logger.warning(
            "Topology fallback skipped: %s (path=%s)", exc, exc.path
        )
        return {}
    except Exception:  # noqa: BLE001
        logger.warning("Topology fallback skipped (unexpected error)", exc_info=True)
        return {}

    services = topology.service_map
    applied: dict[str, str] = {}
    fields_set = settings.model_fields_set
    for mapping in URL_FALLBACK_FIELDS:
        if not hasattr(settings, mapping.settings_field):
            continue
        # Env wins: if the operator set ``AQP_<FIELD>``, leave it alone.
        if mapping.settings_field in fields_set:
            continue
        service = services.get(mapping.service_id)
        if service is None:
            continue
        url = service.endpoint(mapping.endpoint_name)
        if not url:
            continue
        try:
            object.__setattr__(settings, mapping.settings_field, url)
        except Exception:  # noqa: BLE001
            logger.debug(
                "topology fallback could not assign %s",
                mapping.settings_field,
                exc_info=True,
            )
            continue
        applied[mapping.settings_field] = url
    if applied:
        logger.info(
            "Topology fallback applied to %d Settings fields", len(applied)
        )
    return applied


def topology_fallback_mappings() -> Iterable[_Mapping]:
    """Read-only iteration of the mapping table. Test helper."""
    return URL_FALLBACK_FIELDS


__all__ = [
    "apply_topology_fallback",
    "topology_fallback_mappings",
]
