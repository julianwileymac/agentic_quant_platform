"""Push AQP EntityAspect rows to DataHub via MetadataChangeProposalWrapper."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, or_, select

from aqp.auth.contextvars import get_context_or_default
from aqp.data.datahub.aspect_mapping import (
    aqp_urn_to_datahub_entity_urn,
    build_datahub_aspect,
)
from aqp.data.datahub.client import DataHubUnavailableError, get_client
from aqp.data.datahub.emitter import _finalize_log_entry, _start_log_entry
from aqp.metadata.urn import parse_urn as parse_aqp_urn
from aqp.persistence.db import get_session
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity

logger = logging.getLogger(__name__)

_SDK_UNAVAILABLE_ERROR = "datahub SDK unavailable"


def push_aspect(
    *,
    urn: str,
    aspect_name: str | None = None,
    version: int | None = None,
) -> dict[str, Any]:
    """Push one URN's current (or pinned-version) aspects to DataHub."""
    try:
        parse_aqp_urn(urn)
    except ValueError as exc:
        return {"emitted": False, "n_aspects": 0, "errors": [str(exc)], "error": str(exc)}

    workspace_id, project_id = _active_tenancy()
    with get_session() as session:
        entity = session.get(MetadataEntity, urn)
        if entity is None:
            error = f"metadata entity not found for urn={urn}"
            return {"emitted": False, "n_aspects": 0, "errors": [error], "error": error}

        stmt = select(EntityAspect).where(EntityAspect.urn == urn)
        stmt = _apply_tenancy_filters(
            stmt,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        if aspect_name:
            stmt = stmt.where(EntityAspect.aspect_name == aspect_name)
        if version is not None:
            stmt = stmt.where(EntityAspect.version == int(version))
        stmt = stmt.order_by(EntityAspect.aspect_name.asc(), desc(EntityAspect.version))
        rows = session.execute(stmt).scalars().all()

    if not rows:
        details = (
            f"aspect rows not found for urn={urn}, aspect_name={aspect_name}, version={version}"
        )
        return {"emitted": False, "n_aspects": 0, "errors": [details], "error": details}

    if version is None:
        rows = _select_latest_per_aspect(rows)

    emitter, wrapper, prep_error = _prepare_emitter_and_wrapper()
    if prep_error or emitter is None or wrapper is None:
        return {
            "emitted": False,
            "n_aspects": 0,
            "errors": [prep_error or _SDK_UNAVAILABLE_ERROR],
            "error": prep_error or _SDK_UNAVAILABLE_ERROR,
        }

    emitted_count = 0
    errors: list[str] = []
    for row in rows:
        result = _emit_aspect_row(row=row, emitter=emitter, wrapper=wrapper)
        if result.get("emitted"):
            emitted_count += 1
            continue
        errors.append(
            (
                f"{row.urn}:{row.aspect_name}:v{row.version}: "
                f"{result.get('error') or 'emit failed'}"
            )
        )

    return {
        "emitted": emitted_count > 0,
        "n_aspects": emitted_count,
        "errors": errors,
    }


def push_all_aspects(
    *,
    entity_type: str | None = None,
    since: datetime | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    """Batch-push EntityAspect rows to DataHub for the active tenant."""
    workspace_id, project_id = _active_tenancy()
    with get_session() as session:
        stmt = (
            select(EntityAspect)
            .join(MetadataEntity, MetadataEntity.urn == EntityAspect.urn)
            .order_by(desc(EntityAspect.created_at))
            .limit(limit)
        )
        stmt = _apply_tenancy_filters(
            stmt,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        if entity_type:
            stmt = stmt.where(MetadataEntity.entity_type == entity_type)
        if since is not None:
            stmt = stmt.where(EntityAspect.created_at >= since)
        rows = session.execute(stmt).scalars().all()

    if not rows:
        return {"emitted_count": 0, "skipped_count": 0, "errors": []}

    emitter, wrapper, prep_error = _prepare_emitter_and_wrapper()
    if prep_error or emitter is None or wrapper is None:
        return {
            "emitted_count": 0,
            "skipped_count": len(rows),
            "errors": [prep_error or _SDK_UNAVAILABLE_ERROR],
            "error": prep_error or _SDK_UNAVAILABLE_ERROR,
        }

    emitted_count = 0
    skipped_count = 0
    errors: list[str] = []
    for row in rows:
        result = _emit_aspect_row(row=row, emitter=emitter, wrapper=wrapper)
        if result.get("emitted"):
            emitted_count += 1
        else:
            skipped_count += 1
            errors.append(
                (
                    f"{row.urn}:{row.aspect_name}:v{row.version}: "
                    f"{result.get('error') or 'emit failed'}"
                )
            )

    return {
        "emitted_count": emitted_count,
        "skipped_count": skipped_count,
        "errors": errors,
    }


def _load_mcp_wrapper() -> type[Any] | None:
    try:
        from datahub.emitter.mcp import MetadataChangeProposalWrapper
    except ImportError:
        return None
    except Exception:
        return None
    return MetadataChangeProposalWrapper


def _active_tenancy() -> tuple[str | None, str | None]:
    try:
        ctx = get_context_or_default()
    except Exception:
        return None, None
    return ctx.workspace_id, ctx.project_id


def _apply_tenancy_filters(stmt: Any, *, workspace_id: str | None, project_id: str | None) -> Any:
    if workspace_id:
        stmt = stmt.where(
            or_(
                EntityAspect.workspace_id == workspace_id,
                EntityAspect.workspace_id.is_(None),
            )
        )
    else:
        stmt = stmt.where(EntityAspect.workspace_id.is_(None))
    if project_id:
        stmt = stmt.where(
            or_(
                EntityAspect.project_id == project_id,
                EntityAspect.project_id.is_(None),
            )
        )
    return stmt


def _prepare_emitter_and_wrapper() -> tuple[Any | None, type[Any] | None, str | None]:
    try:
        emitter = get_client().emitter()
    except DataHubUnavailableError as exc:
        message = str(exc) or _SDK_UNAVAILABLE_ERROR
        if "SDK" in message or "acryl-datahub" in message:
            message = _SDK_UNAVAILABLE_ERROR
        return None, None, message
    except Exception as exc:  # noqa: BLE001
        return None, None, str(exc)

    wrapper = _load_mcp_wrapper()
    if wrapper is None:
        return None, None, _SDK_UNAVAILABLE_ERROR
    return emitter, wrapper, None


def _emit_mcp(emitter: Any, event: Any) -> None:
    if hasattr(emitter, "emit_mcp"):
        emitter.emit_mcp(event)
        return
    emitter.emit(event)


def _emit_aspect_row(
    *,
    row: EntityAspect,
    emitter: Any,
    wrapper: type[Any],
) -> dict[str, Any]:
    datahub_urn = aqp_urn_to_datahub_entity_urn(row.urn)
    log_entry = _start_log_entry(
        urn=datahub_urn,
        payload={
            "aqp_urn": row.urn,
            "aspect_name": row.aspect_name,
            "version": row.version,
            "payload": row.payload or {},
        },
        direction="push",
    )
    try:
        aspect = build_datahub_aspect(row.aspect_name, dict(row.payload or {}))
        if aspect is None:
            _finalize_log_entry(log_entry, status="error", error=_SDK_UNAVAILABLE_ERROR)
            return {
                "emitted": False,
                "urn": row.urn,
                "aspect_name": row.aspect_name,
                "version": row.version,
                "error": _SDK_UNAVAILABLE_ERROR,
            }

        event = wrapper(entityUrn=datahub_urn, aspect=aspect)
        _emit_mcp(emitter, event)
        _finalize_log_entry(log_entry, status="ok")
        return {
            "emitted": True,
            "urn": row.urn,
            "datahub_urn": datahub_urn,
            "aspect_name": row.aspect_name,
            "version": row.version,
        }
    except Exception as exc:  # noqa: BLE001
        _finalize_log_entry(log_entry, status="error", error=str(exc))
        return {
            "emitted": False,
            "urn": row.urn,
            "aspect_name": row.aspect_name,
            "version": row.version,
            "error": str(exc),
        }


def _select_latest_per_aspect(rows: list[EntityAspect]) -> list[EntityAspect]:
    selected: list[EntityAspect] = []
    seen: set[str] = set()
    for row in rows:
        if row.aspect_name in seen:
            continue
        seen.add(row.aspect_name)
        selected.append(row)
    return selected


__all__ = ["push_all_aspects", "push_aspect"]
