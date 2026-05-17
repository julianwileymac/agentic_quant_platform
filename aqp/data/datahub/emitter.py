"""Push AQP catalog state to DataHub."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from aqp.config import settings
from aqp.data.datahub.client import DataHubUnavailableError, get_client
from aqp.data.datahub.mapping import iceberg_dataset_urn
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog

logger = logging.getLogger(__name__)


def push_dataset(
    *,
    urn: str | None = None,
    payload: dict[str, Any] | None = None,
    catalog_id: str | None = None,
) -> dict[str, Any]:
    """Emit a Dataset MCE to DataHub.

    Either ``urn`` + ``payload`` are provided directly, or ``catalog_id``
    is used to look up the :class:`DatasetCatalog` row and synthesize
    both. Best-effort: returns ``{"emitted": False, "error": ...}``
    when the SDK isn't installed or DataHub isn't reachable.
    """
    payload = dict(payload or {})
    if catalog_id and not urn:
        with get_session() as session:
            row = session.execute(
                select(DatasetCatalog).where(DatasetCatalog.id == catalog_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return {"emitted": False, "error": f"catalog row {catalog_id} missing"}
            urn = row.datahub_urn or iceberg_dataset_urn(
                row.iceberg_identifier or row.name
            )
            payload.setdefault("name", row.iceberg_identifier or row.name)
            payload.setdefault("description", row.description or "")
            payload.setdefault("tags", list(row.tags or []))
            payload.setdefault("custom_properties", {
                "provider": row.provider,
                "domain": row.domain,
                "compute_backend": row.compute_backend,
                "load_mode": row.load_mode,
                "frequency": row.frequency,
            })
            payload.setdefault("schema", row.schema_json or {})

    if not urn:
        return {"emitted": False, "error": "missing urn"}

    log_entry = _start_log_entry(urn=urn, payload=payload, direction="push")

    try:
        client = get_client()
        emitter = client.emitter()
    except DataHubUnavailableError as exc:
        logger.warning("datahub emitter unavailable: %s", exc)
        _finalize_log_entry(log_entry, status="error", error=str(exc))
        return {"emitted": False, "error": str(exc)}

    try:
        from datahub.emitter.mce_builder import (
            make_dataset_urn_with_platform_instance,  # noqa: F401
        )
        from datahub.metadata.schema_classes import (
            DatasetPropertiesClass,
            GlobalTagsClass,
            TagAssociationClass,
        )
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
    except Exception as exc:  # noqa: BLE001 - older SDKs
        logger.warning("datahub schema classes unavailable: %s", exc)
        _finalize_log_entry(log_entry, status="error", error=str(exc))
        return {"emitted": False, "error": str(exc)}

    try:
        properties = DatasetPropertiesClass(
            description=str(payload.get("description") or ""),
            customProperties={
                str(k): "" if v is None else str(v)
                for k, v in (payload.get("custom_properties") or {}).items()
            },
            name=payload.get("name"),
        )
        tags = GlobalTagsClass(
            tags=[
                TagAssociationClass(tag=f"urn:li:tag:{t}")
                for t in (payload.get("tags") or [])
                if t
            ]
        )
        events = [
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=properties),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=tags),
        ]
        for evt in events:
            emitter.emit(evt)
        _finalize_log_entry(log_entry, status="ok")
        return {"emitted": True, "urn": urn, "events": len(events)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("datahub push failed for %s: %s", urn, exc)
        _finalize_log_entry(log_entry, status="error", error=str(exc))
        return {"emitted": False, "urn": urn, "error": str(exc)}


def push_dagster_lineage(
    *,
    asset_key: str,
    upstream_urns: list[str] | None = None,
    downstream_urns: list[str] | None = None,
) -> dict[str, Any]:
    """Emit DataFlow + DataJob URNs for a Dagster asset key."""
    flow_urn = f"urn:li:dataFlow:(dagster,{asset_key},{settings.datahub_env or 'PROD'})"
    job_urn = (
        f"urn:li:dataJob:({flow_urn},{asset_key.split('.')[-1]})"
    )
    log_entry = _start_log_entry(
        urn=flow_urn,
        payload={
            "asset_key": asset_key,
            "upstream": upstream_urns or [],
            "downstream": downstream_urns or [],
        },
        direction="push",
    )
    try:
        client = get_client()
        emitter = client.emitter()
    except DataHubUnavailableError as exc:
        _finalize_log_entry(log_entry, status="error", error=str(exc))
        return {"emitted": False, "error": str(exc)}
    try:
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
        from datahub.metadata.schema_classes import (
            DataFlowInfoClass,
            DataJobInfoClass,
            DataJobInputOutputClass,
        )

        emitter.emit(
            MetadataChangeProposalWrapper(
                entityUrn=flow_urn,
                aspect=DataFlowInfoClass(
                    name=asset_key,
                    description=f"Dagster asset {asset_key}",
                ),
            )
        )
        emitter.emit(
            MetadataChangeProposalWrapper(
                entityUrn=job_urn,
                aspect=DataJobInfoClass(
                    name=asset_key,
                    type="DAGSTER",
                ),
            )
        )
        emitter.emit(
            MetadataChangeProposalWrapper(
                entityUrn=job_urn,
                aspect=DataJobInputOutputClass(
                    inputDatasets=list(upstream_urns or []),
                    outputDatasets=list(downstream_urns or []),
                ),
            )
        )
        _finalize_log_entry(log_entry, status="ok")
        return {"emitted": True, "flow_urn": flow_urn, "job_urn": job_urn}
    except Exception as exc:  # noqa: BLE001
        _finalize_log_entry(log_entry, status="error", error=str(exc))
        return {"emitted": False, "error": str(exc)}


def push_all(*, limit: int = 1000) -> dict[str, Any]:
    """Emit a Dataset MCE for every :class:`DatasetCatalog` row."""
    emitted = 0
    errors: list[str] = []
    with get_session() as session:
        rows = (
            session.execute(select(DatasetCatalog).limit(limit))
            .scalars()
            .all()
        )
    for row in rows:
        result = push_dataset(catalog_id=row.id)
        if result.get("emitted"):
            emitted += 1
        elif result.get("error"):
            errors.append(f"{row.id}: {result['error']}")
    return {"emitted": emitted, "total": len(rows), "errors": errors}


# ---------------------------------------------------------------------------
# Sync log helpers
# ---------------------------------------------------------------------------


def _start_log_entry(
    *, urn: str, payload: dict[str, Any], direction: str
) -> dict[str, Any]:
    try:
        from aqp.persistence.models_pipelines import DatahubSyncLog

        with get_session() as session:
            row = DatahubSyncLog(
                direction=direction,
                target=urn[:240],
                urn=urn,
                platform=settings.datahub_platform,
                platform_instance=settings.datahub_platform_instance,
                status="running",
                payload=payload,
                started_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            return {"id": row.id}
    except Exception as exc:  # noqa: BLE001
        logger.debug("datahub sync log skipped: %s", exc)
        return {}


def _finalize_log_entry(
    entry: dict[str, Any],
    *,
    status: str,
    error: str | None = None,
) -> None:
    log_id = entry.get("id")
    if not log_id:
        return
    try:
        from aqp.persistence.models_pipelines import DatahubSyncLog

        with get_session() as session:
            row = session.get(DatahubSyncLog, log_id)
            if row is None:
                return
            row.status = status
            row.error = error
            row.finished_at = datetime.utcnow()
            session.add(row)
    except Exception as exc:  # noqa: BLE001
        logger.debug("datahub sync log finalize skipped: %s", exc)


__all__ = [
    "push_all",
    "push_dagster_lineage",
    "push_dataset",
]
