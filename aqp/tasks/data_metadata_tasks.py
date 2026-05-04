"""Metadata-only sync tasks for data pipeline control planes."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from aqp.config import settings
from aqp.data.entities import registry as entity_registry
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog
from aqp.persistence.models_data_control import (
    DatasetPipelineConfigRow,
    SourceLibraryEntry,
    SourceMetadataVersion,
)
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.data_metadata_tasks.sync_data_metadata")
def sync_data_metadata(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sync metadata only from Airbyte, Dagster, and dbt."""
    task_id = self.request.id or "data-metadata-sync"
    payload = dict(payload or {})
    targets = [str(t).lower() for t in (payload.get("targets") or ["airbyte", "dagster", "dbt"])]
    enrich = bool(payload.get("enrich_with_llm"))
    emit(task_id, "start", f"Syncing metadata targets={targets}")
    result: dict[str, Any] = {"targets": {}, "enriched": enrich}
    try:
        if "airbyte" in targets:
            emit(task_id, "airbyte", "Reading Airbyte control-plane metadata")
            result["targets"]["airbyte"] = _sync_airbyte_metadata(
                discover_schemas=bool(payload.get("discover_airbyte_schemas", True)),
                enrich=enrich,
            )
        if "dagster" in targets:
            emit(task_id, "dagster", "Reading Dagster asset and run metadata")
            result["targets"]["dagster"] = _sync_dagster_metadata(enrich=enrich)
        if "dbt" in targets:
            emit(task_id, "dbt", "Reading dbt model artifacts")
            result["targets"]["dbt"] = _sync_dbt_metadata(enrich=enrich)
        emit_done(task_id, result)
        return result
    except Exception as exc:
        logger.exception("sync_data_metadata failed")
        emit_error(task_id, str(exc))
        raise


def _sync_airbyte_metadata(*, discover_schemas: bool, enrich: bool) -> dict[str, Any]:
    from aqp.data.sources.registry import upsert_data_source
    from aqp.services.airbyte_client import AirbyteClient

    client = AirbyteClient()
    workspaces = _safe_call(client.list_workspaces)
    sources = _list_from_payload(_safe_call(client.list_sources), "sources")
    destinations = _list_from_payload(_safe_call(client.list_destinations), "destinations")
    connections = _list_from_payload(_safe_call(client.list_connections), "connections")

    persisted_sources = 0
    schemas: dict[str, Any] = {}
    for entry in sources:
        source_id = _first(entry, "sourceId", "source_id", "id")
        name = _first(entry, "name", "sourceName", "source_name") or source_id or "airbyte_source"
        source_name = _slug(f"airbyte_{name}", max_len=64)
        schema_payload: dict[str, Any] = {}
        if discover_schemas and source_id:
            schema_payload = _safe_call(client.discover_source_schema, str(source_id))
            schemas[str(source_id)] = schema_payload
        metadata = {
            "airbyte": entry,
            "schema": schema_payload,
            "workspace": workspaces,
        }
        if enrich:
            metadata["llm_summary"] = _enrich_metadata("Airbyte source", metadata)
        row = upsert_data_source(
            name=source_name,
            display_name=f"Airbyte: {name}",
            kind="airbyte",
            vendor="Airbyte",
            auth_type="airbyte",
            base_url=settings.airbyte_api_url or settings.airbyte_base_url,
            protocol="airbyte/public-api-v1",
            capabilities={"domains": ["metadata.airbyte"], "streams": _streams_from_schema(schema_payload)},
            credentials_ref="AQP_AIRBYTE_AUTH_TOKEN",
            enabled=True,
            meta=metadata,
        )
        _persist_source_snapshot(
            source_id=row.get("id"),
            source_name=source_name,
            display_name=row.get("display_name") or f"Airbyte: {name}",
            metadata=metadata,
            import_uri=f"airbyte://source/{source_id}" if source_id else None,
            default_node="source.rest_api",
            tags=["airbyte", "metadata"],
            change_kind="metadata_sync",
        )
        persisted_sources += 1

    configs = 0
    for connection in connections:
        name = _first(connection, "name", "connectionName", "connection_id", "connectionId", "id") or "airbyte_connection"
        _persist_dataset_pipeline_config(
            name=_slug(f"airbyte_{name}", max_len=160),
            config={
                "kind": "airbyte_connection",
                "connection": connection,
                "destinations": destinations,
                "metadata_only": True,
            },
            sinks=["sink.iceberg", "sink.parquet"],
            automations=[connection.get("schedule") or connection.get("scheduleData") or {}],
            tags=["airbyte", "metadata"],
        )
        configs += 1
    graph_result = _sync_airbyte_graph(
        workspaces=workspaces,
        sources=sources,
        destinations=destinations,
        connections=connections,
    )

    return {
        "sources": len(sources),
        "destinations": len(destinations),
        "connections": len(connections),
        "persisted_sources": persisted_sources,
        "pipeline_configs": configs,
        "schemas": len(schemas),
        "graph": graph_result,
    }


def _sync_dagster_metadata(*, enrich: bool) -> dict[str, Any]:
    url = _dagster_graphql_url()
    if not url:
        return {"source": "not_configured", "assets": 0, "runs": 0}
    assets_payload = _graphql(
        url,
        "query { assetNodes { assetKey { path } description groupName computeKind isPartitioned } }",
    )
    runs_payload = _graphql(
        url,
        "query Runs($limit: Int!) { runsOrError(limit: $limit) { ... on Runs { results { runId pipelineName status startTime endTime } } } }",
        variables={"limit": 50},
    )
    assets = ((assets_payload.get("data") or {}).get("assetNodes") or [])
    runs = (((runs_payload.get("data") or {}).get("runsOrError") or {}).get("results") or [])
    for asset in assets:
        key = "/".join((asset.get("assetKey") or {}).get("path") or [])
        if not key:
            continue
        metadata = {"kind": "dagster_asset", "asset": asset, "runs": runs[:10]}
        if enrich:
            metadata["llm_summary"] = _enrich_metadata("Dagster asset", metadata)
        _persist_dataset_pipeline_config(
            name=_slug(f"dagster_{key.replace('/', '_')}", max_len=160),
            config=metadata,
            sinks=[],
            automations=[{"kind": "dagster_asset", "asset_key": key}],
            tags=["dagster", "metadata", str(asset.get("groupName") or "asset")],
        )
    graph_result = _sync_dagster_graph(assets=assets, runs=runs)
    return {"source": "graphql", "assets": len(assets), "runs": len(runs), "graph": graph_result}


def _sync_airbyte_graph(
    *,
    workspaces: dict[str, Any],
    sources: list[dict[str, Any]],
    destinations: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> dict[str, int]:
    """Mirror Airbyte control-plane metadata into the entity graph."""
    upserts = 0
    relations = 0
    workspace_items = _list_from_payload(workspaces, "workspaces")
    workspace_entity_ids: list[str] = []
    for workspace in workspace_items:
        workspace_id = _first(workspace, "workspaceId", "workspace_id", "id")
        if not workspace_id:
            continue
        entity = entity_registry.upsert_entity(
            kind="airbyte_workspace",
            canonical_name=str(_first(workspace, "name", "workspaceName") or workspace_id),
            primary_identifier=str(workspace_id),
            primary_identifier_scheme="airbyte_workspace_id",
            attributes={"airbyte": workspace},
            tags=["airbyte", "workspace", "service"],
            source_dataset="airbyte",
            source_extractor="aqp.metadata_sync",
        )
        if entity:
            workspace_entity_ids.append(str(entity["id"]))
            upserts += 1

    source_entities: dict[str, str] = {}
    for source in sources:
        source_id = _first(source, "sourceId", "source_id", "id")
        if not source_id:
            continue
        entity = entity_registry.upsert_entity(
            kind="airbyte_source",
            canonical_name=str(_first(source, "name", "sourceName", "source_name") or source_id),
            primary_identifier=str(source_id),
            primary_identifier_scheme="airbyte_source_id",
            attributes={"airbyte": source},
            tags=["airbyte", "source", "connector"],
            source_dataset="airbyte",
            source_extractor="aqp.metadata_sync",
        )
        if entity:
            source_entities[str(source_id)] = str(entity["id"])
            upserts += 1

    destination_entities: dict[str, str] = {}
    for destination in destinations:
        destination_id = _first(destination, "destinationId", "destination_id", "id")
        if not destination_id:
            continue
        entity = entity_registry.upsert_entity(
            kind="airbyte_destination",
            canonical_name=str(
                _first(destination, "name", "destinationName", "destination_name") or destination_id
            ),
            primary_identifier=str(destination_id),
            primary_identifier_scheme="airbyte_destination_id",
            attributes={"airbyte": destination},
            tags=["airbyte", "destination", "connector"],
            source_dataset="airbyte",
            source_extractor="aqp.metadata_sync",
        )
        if entity:
            destination_entities[str(destination_id)] = str(entity["id"])
            upserts += 1

    for connection in connections:
        connection_id = _first(connection, "connectionId", "connection_id", "id")
        if not connection_id:
            continue
        entity = entity_registry.upsert_entity(
            kind="airbyte_connection",
            canonical_name=str(_first(connection, "name", "connectionName") or connection_id),
            primary_identifier=str(connection_id),
            primary_identifier_scheme="airbyte_connection_id",
            attributes={"airbyte": connection},
            tags=["airbyte", "connection", "pipeline"],
            source_dataset="airbyte",
            source_extractor="aqp.metadata_sync",
        )
        if not entity:
            continue
        upserts += 1
        connection_entity_id = str(entity["id"])
        source_id = str(_first(connection, "sourceId", "source_id") or "")
        destination_id = str(_first(connection, "destinationId", "destination_id") or "")
        for workspace_entity_id in workspace_entity_ids:
            if entity_registry.add_entity_relation(
                subject_id=workspace_entity_id,
                predicate="OWNS_AIRBYTE_CONNECTION",
                object_id=connection_entity_id,
                provenance="airbyte",
            ):
                relations += 1
        if source_id in source_entities and entity_registry.add_entity_relation(
            subject_id=source_entities[source_id],
            predicate="FEEDS_CONNECTION",
            object_id=connection_entity_id,
            provenance="airbyte",
            properties={"connection_id": connection_id},
        ):
            relations += 1
        if destination_id in destination_entities and entity_registry.add_entity_relation(
            subject_id=connection_entity_id,
            predicate="WRITES_TO_DESTINATION",
            object_id=destination_entities[destination_id],
            provenance="airbyte",
            properties={"connection_id": connection_id},
        ):
            relations += 1
    return {"upserts": upserts, "relations": relations}


def _sync_dagster_graph(
    *,
    assets: list[dict[str, Any]],
    runs: list[dict[str, Any]],
) -> dict[str, int]:
    """Mirror Dagster assets/runs into the entity graph."""
    upserts = 0
    relations = 0
    asset_entities: dict[str, str] = {}
    for asset in assets:
        key = "/".join((asset.get("assetKey") or {}).get("path") or [])
        if not key:
            continue
        entity = entity_registry.upsert_entity(
            kind="dagster_asset",
            canonical_name=key,
            primary_identifier=key,
            primary_identifier_scheme="dagster_asset_key",
            description=asset.get("description"),
            attributes={"dagster": asset},
            tags=["dagster", "asset", str(asset.get("groupName") or "default")],
            source_dataset="dagster",
            source_extractor="aqp.metadata_sync",
        )
        if not entity:
            continue
        upserts += 1
        asset_entity_id = str(entity["id"])
        asset_entities[key] = asset_entity_id
        try:
            with get_session() as session:
                rows = (
                    session.execute(
                        select(DatasetCatalog).where(DatasetCatalog.dagster_asset_key == key).limit(20)
                    )
                    .scalars()
                    .all()
                )
                for dataset in rows:
                    entity_registry.attach_entity_to_dataset(
                        entity_id=asset_entity_id,
                        dataset_catalog_id=dataset.id,
                        iceberg_identifier=dataset.iceberg_identifier,
                        role="materializes",
                        meta={"dagster_asset_key": key, "dataset_name": dataset.name},
                    )
                    relations += 1
        except Exception:  # noqa: BLE001
            logger.debug("dagster dataset graph link skipped", exc_info=True)

    for run in runs:
        run_id = _first(run, "runId", "run_id", "id")
        if not run_id:
            continue
        entity = entity_registry.upsert_entity(
            kind="dagster_run",
            canonical_name=str(run_id),
            primary_identifier=str(run_id),
            primary_identifier_scheme="dagster_run_id",
            attributes={"dagster": run},
            tags=["dagster", "run", str(run.get("status") or "unknown").lower()],
            source_dataset="dagster",
            source_extractor="aqp.metadata_sync",
        )
        if not entity:
            continue
        upserts += 1
        pipeline_name = str(run.get("pipelineName") or "")
        if pipeline_name in asset_entities and entity_registry.add_entity_relation(
            subject_id=str(entity["id"]),
            predicate="MATERIALIZED_ASSET",
            object_id=asset_entities[pipeline_name],
            provenance="dagster",
            properties={"status": run.get("status")},
        ):
            relations += 1
    return {"upserts": upserts, "relations": relations}


def _sync_dbt_metadata(*, enrich: bool) -> dict[str, Any]:
    from aqp.data.dbt import DbtProjectManager, load_manifest_models, load_run_results

    manager = DbtProjectManager.from_settings()
    models = load_manifest_models(manager.project_dir)
    run_results = load_run_results(manager.project_dir)
    for model in models:
        unique_id = str(model.get("unique_id") or model.get("name") or "dbt_model")
        metadata = {"kind": "dbt_model", "model": model, "run_results": run_results}
        if enrich:
            metadata["llm_summary"] = _enrich_metadata("dbt model", metadata)
        _persist_dataset_pipeline_config(
            name=_slug(f"dbt_{unique_id.replace('.', '_')}", max_len=160),
            config=metadata,
            sinks=["sink.dbt_build"],
            automations=[{"kind": "dbt_build", "select": [unique_id]}],
            tags=["dbt", "metadata", *(model.get("tags") or [])],
        )
    return {"models": len(models), "run_results": bool(run_results)}


def _persist_source_snapshot(
    *,
    source_id: str | None,
    source_name: str,
    display_name: str,
    metadata: dict[str, Any],
    import_uri: str | None,
    default_node: str,
    tags: list[str],
    change_kind: str,
) -> None:
    try:
        with get_session() as session:
            current_version = (
                session.execute(
                    select(func.max(SourceMetadataVersion.version)).where(
                        SourceMetadataVersion.source_name == source_name
                    )
                ).scalar_one()
                or 0
            )
            version = int(current_version) + 1
            entry = session.execute(
                select(SourceLibraryEntry).where(SourceLibraryEntry.source_name == source_name).limit(1)
            ).scalar_one_or_none()
            if entry is None:
                entry = SourceLibraryEntry(source_name=source_name, display_name=display_name)
            entry.source_id = source_id
            entry.display_name = display_name
            entry.import_uri = import_uri
            entry.default_node = default_node
            entry.metadata_json = metadata
            entry.pipeline_hints = {"default_node": default_node, "metadata_only": True}
            entry.setup_steps = [{"id": "review", "label": "Review synced metadata", "status": "pending"}]
            entry.tags = list(tags)
            entry.version = version
            entry.updated_at = datetime.utcnow()
            session.add(entry)
            session.add(
                SourceMetadataVersion(
                    source_id=source_id,
                    source_name=source_name,
                    version=version,
                    change_kind=change_kind,
                    import_uri=import_uri,
                    metadata_json=metadata,
                    tags=list(tags),
                )
            )
    except Exception:
        logger.debug("source metadata snapshot skipped for %s", source_name, exc_info=True)


def _persist_dataset_pipeline_config(
    *,
    name: str,
    config: dict[str, Any],
    sinks: list[str],
    automations: list[dict[str, Any]],
    tags: list[str],
) -> None:
    try:
        with get_session() as session:
            current_version = (
                session.execute(
                    select(func.max(DatasetPipelineConfigRow.version)).where(
                        DatasetPipelineConfigRow.name == name
                    )
                ).scalar_one()
                or 0
            )
            session.query(DatasetPipelineConfigRow).filter(
                DatasetPipelineConfigRow.name == name,
                DatasetPipelineConfigRow.is_active.is_(True),
            ).update({"is_active": False, "updated_at": datetime.utcnow()})
            session.add(
                DatasetPipelineConfigRow(
                    name=name,
                    version=int(current_version) + 1,
                    status="synced",
                    config_json=config,
                    sinks=list(sinks),
                    automations=[dict(item) for item in automations if item],
                    tags=list(tags),
                    is_active=True,
                    created_by="metadata_sync",
                )
            )
    except Exception:
        logger.debug("dataset pipeline config snapshot skipped for %s", name, exc_info=True)


def _enrich_metadata(label: str, payload: dict[str, Any]) -> str:
    try:
        from aqp.llm.providers.router import router_complete

        result = router_complete(
            settings.llm_director_provider,
            settings.llm_director_model,
            prompt=(
                f"Summarize this {label} metadata in one concise sentence for a data catalog. "
                f"Do not invent fields.\n\n{str(payload)[:6000]}"
            ),
            temperature=settings.llm_director_temperature,
            max_tokens=160,
        )
        return result.content.strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("metadata LLM enrichment skipped: %s", exc)
        return ""


def _safe_call(fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        data = fn(*args, **kwargs)
        return data if isinstance(data, dict) else {"data": data}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _list_from_payload(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = payload.get(key) or payload.get("data") or payload.get("items") or []
    if isinstance(raw, dict):
        raw = raw.get(key) or raw.get("items") or []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _streams_from_schema(payload: dict[str, Any]) -> list[str]:
    catalog = payload.get("catalog") or payload.get("connectionSpecification") or payload
    streams = catalog.get("streams") if isinstance(catalog, dict) else []
    return [
        str((stream.get("stream") or {}).get("name") or stream.get("name"))
        for stream in (streams or [])
        if isinstance(stream, dict)
    ]


def _first(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _slug(raw: str, *, max_len: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()
    return (slug or "metadata")[:max_len]


def _dagster_graphql_url() -> str | None:
    url = settings.dagster_graphql_url or settings.dagster_webserver_url
    if not url:
        return None
    return url if url.endswith("/graphql") else url.rstrip("/") + "/graphql"


def _graphql(url: str, query: str, *, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    import httpx

    with httpx.Client(timeout=15.0) as client:
        response = client.post(url, json={"query": query, "variables": variables or {}})
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}


__all__ = ["sync_data_metadata"]
