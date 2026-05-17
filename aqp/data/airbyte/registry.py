"""Curated Airbyte connector registry for AQP."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from aqp.data.airbyte.models import (
    AirbyteConnectorDefinition,
    AirbyteStreamSpec,
    ConnectorKind,
    ConnectorRuntime,
    SyncMode,
)


def list_connectors(
    *,
    kind: ConnectorKind | str | None = None,
    tag: str | None = None,
) -> list[AirbyteConnectorDefinition]:
    """Return registered connector definitions, optionally filtered."""
    connector_kind = ConnectorKind(kind) if isinstance(kind, str) else kind
    rows = []
    for connector in _catalog():
        if connector_kind and connector.kind != connector_kind:
            continue
        if tag and tag not in connector.tags:
            continue
        rows.append(connector)
    return rows


def get_connector(connector_id: str) -> AirbyteConnectorDefinition:
    """Return one connector definition by AQP id."""
    lookup = {connector.id: connector for connector in _catalog()}
    key = connector_id.strip().lower()
    if key not in lookup:
        raise KeyError(connector_id)
    return lookup[key]


def connector_summary() -> dict[str, Any]:
    """Small summary for UI cards and health screens."""
    connectors = _catalog()
    return {
        "total": len(connectors),
        "sources": sum(1 for item in connectors if item.kind == ConnectorKind.SOURCE),
        "destinations": sum(1 for item in connectors if item.kind == ConnectorKind.DESTINATION),
        "embedded": sum(1 for item in connectors if item.runtime != ConnectorRuntime.FULL_AIRBYTE),
        "full_airbyte": sum(1 for item in connectors if item.runtime != ConnectorRuntime.EMBEDDED),
        "tags": sorted({tag for item in connectors for tag in item.tags}),
    }


def stream_entity_mappings(connector_id: str) -> list[dict[str, Any]]:
    """Expose how connector streams map into the entity registry."""
    connector = get_connector(connector_id)
    mappings: list[dict[str, Any]] = []
    for stream in connector.streams:
        if not stream.entity_kind:
            continue
        mappings.append(
            {
                "connector_id": connector.id,
                "stream": stream.name,
                "entity_kind": stream.entity_kind,
                "identifier_fields": list(stream.entity_identifier_fields),
            }
        )
    return mappings


@lru_cache(maxsize=1)
def _catalog() -> tuple[AirbyteConnectorDefinition, ...]:
    return (
        _source(
            "alpha-vantage",
            "Alpha Vantage",
            "Financial market data, fundamentals, and intraday time series.",
            tags=["financial", "market-data", "rest"],
            package="source-alpha-vantage",
            streams=[
                _stream("time_series_intraday", entity_kind="instrument", ids=["symbol"]),
                _stream("company_overview", entity_kind="issuer", ids=["symbol"]),
                _stream("earnings", entity_kind="issuer", ids=["symbol"]),
            ],
        ),
        _source(
            "yfinance",
            "Yahoo Finance",
            "Yahoo Finance OHLCV, actions, and issuer fundamentals.",
            tags=["financial", "market-data", "rest"],
            package="source-yfinance",
            streams=[
                _stream("ohlcv_bars", entity_kind="instrument", ids=["vt_symbol"]),
                _stream("corporate_actions", entity_kind="instrument", ids=["vt_symbol"]),
                _stream("fundamentals", entity_kind="issuer", ids=["symbol"]),
            ],
        ),
        _source(
            "fred",
            "FRED",
            "Federal Reserve economic series.",
            tags=["financial", "macro", "rest"],
            package="source-fred",
            streams=[_stream("series", entity_kind="economic_series", ids=["series_id"])],
        ),
        _source(
            "ibkr-historical",
            "IBKR Historical",
            "Interactive Brokers historical bars and contract metadata.",
            tags=["financial", "market-data", "broker"],
            package="source-ibkr-historical",
            streams=[
                _stream("historical_bars", entity_kind="instrument", ids=["conid", "symbol"]),
                _stream("contracts", entity_kind="instrument", ids=["conid"]),
            ],
        ),
        _source(
            "sec",
            "SEC EDGAR",
            "Company filings and submission metadata.",
            tags=["financial", "regulatory", "rest"],
            package="source-sec",
            streams=[
                _stream("submissions", entity_kind="issuer", ids=["cik"]),
                _stream("filings", entity_kind="filing", ids=["accession_number"]),
            ],
        ),
        _source(
            "cfpb",
            "CFPB Complaints",
            "Consumer complaint regulatory corpus.",
            tags=["regulatory", "third-order", "rest"],
            package="source-cfpb",
            streams=[_stream("complaints", entity_kind="complaint", ids=["complaint_id"])],
        ),
        _source(
            "fda",
            "openFDA",
            "FDA adverse events, applications, and recalls.",
            tags=["regulatory", "third-order", "rest"],
            package="source-fda",
            streams=[
                _stream("adverse_events", entity_kind="fda_event", ids=["safetyreportid"]),
                _stream("applications", entity_kind="fda_application", ids=["application_number"]),
                _stream("recalls", entity_kind="fda_recall", ids=["recall_number"]),
            ],
        ),
        _source(
            "uspto",
            "USPTO",
            "Patent, assignment, and trademark data.",
            tags=["regulatory", "third-order", "rest"],
            package="source-uspto",
            streams=[
                _stream("patents", entity_kind="patent", ids=["patent_id"]),
                _stream("assignments", entity_kind="assignment", ids=["assignment_id"]),
                _stream("trademarks", entity_kind="trademark", ids=["serial_number"]),
            ],
        ),
        _source(
            "postgres",
            "PostgreSQL",
            "Cluster PostgreSQL source for operational datasets.",
            tags=["deployed-service", "database"],
            package="source-postgres",
            streams=[_stream("tables")],
        ),
        _source(
            "s3-minio",
            "S3 / MinIO",
            "S3-compatible object storage for staged files.",
            tags=["deployed-service", "object-store"],
            package="source-s3",
            streams=[_stream("objects")],
        ),
        _source(
            "kafka",
            "Kafka Metadata",
            "Kafka topic and schema metadata connector.",
            tags=["deployed-service", "streaming"],
            package="source-kafka",
            streams=[_stream("topics"), _stream("schemas")],
        ),
        _source(
            "datahub",
            "DataHub Metadata",
            "Remote DataHub metadata graph connector.",
            tags=["deployed-service", "metadata"],
            package="source-datahub",
            streams=[_stream("datasets"), _stream("lineage")],
        ),
        _source(
            "mlflow",
            "MLflow",
            "Experiments, runs, model versions, and registry metadata.",
            tags=["deployed-service", "mlops"],
            package="source-mlflow",
            streams=[_stream("experiments"), _stream("runs"), _stream("models")],
        ),
        _source(
            "dagster",
            "Dagster",
            "Dagster assets, runs, and materialization events.",
            tags=["deployed-service", "orchestration"],
            package="source-dagster",
            streams=[_stream("assets"), _stream("runs"), _stream("events")],
        ),
        _source(
            "openapi-http",
            "OpenAPI / HTTP",
            "Generic REST and OpenAPI connector for API-first services.",
            tags=["generic", "rest", "embedded"],
            runtime=ConnectorRuntime.HYBRID,
            package="source-openapi-http",
            streams=[_stream("records")],
        ),
        AirbyteConnectorDefinition(
            id="destination-postgres",
            name="PostgreSQL Destination",
            kind=ConnectorKind.DESTINATION,
            runtime=ConnectorRuntime.FULL_AIRBYTE,
            description="Airbyte destination for the cluster PostgreSQL warehouse.",
            python_package="destination-postgres",
            tags=["destination", "database", "deployed-service"],
            capabilities=["append", "append_dedup", "overwrite"],
        ),
        AirbyteConnectorDefinition(
            id="destination-s3-minio",
            name="S3 / MinIO Destination",
            kind=ConnectorKind.DESTINATION,
            runtime=ConnectorRuntime.FULL_AIRBYTE,
            description="Airbyte destination for MinIO staging before AQP materialization.",
            python_package="destination-s3",
            tags=["destination", "object-store", "deployed-service"],
            capabilities=["append", "overwrite"],
        ),
        AirbyteConnectorDefinition(
            id="destination-duckdb-local",
            name="DuckDB Local Cache",
            kind=ConnectorKind.DESTINATION,
            runtime=ConnectorRuntime.EMBEDDED,
            description="Embedded development cache used by PyAirbyte-style dry-runs.",
            tags=["destination", "embedded", "local"],
            capabilities=["append", "overwrite"],
        ),
    )


def _source(
    connector_id: str,
    name: str,
    description: str,
    *,
    tags: list[str],
    package: str,
    streams: list[AirbyteStreamSpec],
    runtime: ConnectorRuntime = ConnectorRuntime.HYBRID,
) -> AirbyteConnectorDefinition:
    return AirbyteConnectorDefinition(
        id=connector_id,
        name=name,
        kind=ConnectorKind.SOURCE,
        runtime=runtime,
        description=description,
        python_package=package,
        tags=tags,
        capabilities=["spec", "check", "discover", "read"],
        streams=streams,
        default_destination="destination-s3-minio",
    )


def _stream(
    name: str,
    *,
    entity_kind: str | None = None,
    ids: list[str] | None = None,
) -> AirbyteStreamSpec:
    return AirbyteStreamSpec(
        name=name,
        supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
        default_sync_mode=SyncMode.INCREMENTAL,
        entity_kind=entity_kind,
        entity_identifier_fields=list(ids or []),
    )


# Cached OSS registry (lazy populated by ``load_airbyte_oss_registry``).
_OSS_CACHE: dict[str, list[AirbyteConnectorDefinition]] = {}


def load_airbyte_oss_registry(
    url: str,
    *,
    timeout_s: float = 30.0,
    api_token: str | None = None,
    overwrite_cache: bool = False,
) -> list[AirbyteConnectorDefinition]:
    """Fetch the Airbyte OSS connector registry JSON and normalise to AQP shape.

    The Airbyte OSS registry is an enormous JSON document hosted at
    ``https://connectors.airbyte.com/files/registries/v0/oss_registry.json``.
    We fetch, project, and merge it into our curated catalog (curated wins on
    name conflict). Result is cached per-URL for the process lifetime so
    subsequent calls are cheap.
    """
    cache_key = url.strip()
    if cache_key in _OSS_CACHE and not overwrite_cache:
        return list(_OSS_CACHE[cache_key])
    try:
        import httpx
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"httpx unavailable: {exc}") from exc
    headers = {"Accept": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    with httpx.Client(timeout=timeout_s, headers=headers) as client:
        r = client.get(cache_key, follow_redirects=True)
        if r.status_code >= 400:
            raise RuntimeError(
                f"airbyte oss registry fetch failed: {r.status_code} {r.text}"
            )
        body = r.json()
    rows: list[AirbyteConnectorDefinition] = []
    sources = body.get("sources") or []
    destinations = body.get("destinations") or []
    for entry in sources:
        try:
            rows.append(_oss_to_definition(entry, kind=ConnectorKind.SOURCE))
        except Exception:  # noqa: BLE001
            continue
    for entry in destinations:
        try:
            rows.append(_oss_to_definition(entry, kind=ConnectorKind.DESTINATION))
        except Exception:  # noqa: BLE001
            continue
    _OSS_CACHE[cache_key] = rows
    return list(rows)


def _oss_to_definition(
    entry: dict[str, Any],
    *,
    kind: ConnectorKind,
) -> AirbyteConnectorDefinition:
    cid = (
        entry.get("connectorName")
        or entry.get("dockerRepository")
        or entry.get("name")
        or "unknown"
    )
    name = entry.get("name") or cid
    desc = entry.get("description") or entry.get("dockerRepository") or ""
    docker = entry.get("dockerRepository") or ""
    docker_tag = entry.get("dockerImageTag") or "latest"
    tags = list(entry.get("tags") or [])
    if entry.get("releaseStage"):
        tags.append(f"release:{entry['releaseStage']}")
    return AirbyteConnectorDefinition(
        id=str(cid).lower(),
        name=str(name),
        kind=kind,
        runtime=ConnectorRuntime.FULL_AIRBYTE,
        description=str(desc),
        docker_repository=docker or None,
        docker_image_tag=docker_tag if docker else None,
        python_package=None,
        tags=tags,
        capabilities=["spec", "check", "discover", "read"],
        streams=[],
    )


def merged_catalog(
    *, oss_url: str | None = None
) -> list[AirbyteConnectorDefinition]:
    """Return curated catalog merged with the cached OSS registry (curated wins)."""
    base = list(_catalog())
    by_id = {c.id: c for c in base}
    if oss_url and oss_url in _OSS_CACHE:
        for connector in _OSS_CACHE[oss_url]:
            by_id.setdefault(connector.id, connector)
    return list(by_id.values())


__all__ = [
    "connector_summary",
    "get_connector",
    "list_connectors",
    "load_airbyte_oss_registry",
    "merged_catalog",
    "stream_entity_mappings",
]
