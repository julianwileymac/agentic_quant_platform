"""CRUD service for the project-scoped sink registry.

Every sink edit re-snapshots the spec into an immutable
:class:`SinkVersionRow` keyed by ``spec_hash`` (mirroring the
``bot_versions`` / ``agent_spec_versions`` pattern). This guarantees
that a manifest referencing a sink can always be replayed against the
exact configuration that produced it.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from aqp.data.engine.manifest import NodeSpec
from aqp.data.fetchers.sinks import (
    SinkKindDescriptor,
    get_sink_descriptor,
    list_sink_kinds,
)
from aqp.persistence import SinkRow, SinkVersionRow

logger = logging.getLogger(__name__)


class SinkNotFoundError(LookupError):
    """Raised when a sink lookup misses."""


class SinkValidationError(ValueError):
    """Raised when the provided sink spec is invalid."""


def _hash_spec(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _spec_payload(row: SinkRow) -> dict[str, Any]:
    return {
        "name": row.name,
        "kind": row.kind,
        "display_name": row.display_name,
        "description": row.description,
        "config_json": dict(row.config_json or {}),
        "tags": list(row.tags or []),
        "documentation_url": row.documentation_url,
        "requires_manifest_node": bool(row.requires_manifest_node),
        "enabled": bool(row.enabled),
    }


def sink_summary(row: SinkRow) -> dict[str, Any]:
    """JSON-friendly summary used by the API."""
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "display_name": row.display_name,
        "description": row.description,
        "config": dict(row.config_json or {}),
        "tags": list(row.tags or []),
        "documentation_url": row.documentation_url,
        "requires_manifest_node": bool(row.requires_manifest_node),
        "current_version": int(row.current_version or 1),
        "enabled": bool(row.enabled),
        "annotations": list(row.annotations or []),
        "meta": dict(row.meta or {}),
        "owner_user_id": row.owner_user_id,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validate_kind(kind: str) -> SinkKindDescriptor:
    desc = get_sink_descriptor(kind)
    if desc is None:
        kinds = ", ".join(d.kind for d in list_sink_kinds())
        raise SinkValidationError(
            f"unknown sink kind {kind!r}; supported kinds: {kinds}"
        )
    return desc


def list_sinks(
    session: Session,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    kind: str | None = None,
    enabled_only: bool = False,
    limit: int | None = None,
) -> list[SinkRow]:
    """Return sink rows ordered by name, optionally filtered."""
    query = session.query(SinkRow)
    if workspace_id is not None:
        query = query.filter(SinkRow.workspace_id == workspace_id)
    if project_id is not None:
        query = query.filter(SinkRow.project_id == project_id)
    if kind:
        query = query.filter(SinkRow.kind == kind)
    if enabled_only:
        query = query.filter(SinkRow.enabled.is_(True))
    query = query.order_by(SinkRow.name.asc())
    if limit is not None:
        query = query.limit(int(limit))
    return list(query)


def get_sink(session: Session, sink_id: str) -> SinkRow:
    """Return a single sink by id, raising :class:`SinkNotFoundError`."""
    row = session.get(SinkRow, sink_id)
    if row is None:
        raise SinkNotFoundError(f"sink {sink_id!r} not found")
    return row


def get_sink_by_name(
    session: Session,
    name: str,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> SinkRow | None:
    """Lookup a sink by (workspace, project, name) tuple."""
    query = session.query(SinkRow).filter(SinkRow.name == name)
    if workspace_id is not None:
        query = query.filter(SinkRow.workspace_id == workspace_id)
    if project_id is not None:
        query = query.filter(SinkRow.project_id == project_id)
    return query.one_or_none()


def list_sink_versions(session: Session, sink_id: str) -> list[SinkVersionRow]:
    """Return version snapshots for a sink, newest first."""
    return list(
        session.query(SinkVersionRow)
        .filter(SinkVersionRow.sink_id == sink_id)
        .order_by(SinkVersionRow.version.desc())
        .all()
    )


def _persist_version(
    session: Session,
    row: SinkRow,
    *,
    notes: str | None,
    created_by: str | None,
) -> SinkVersionRow:
    payload = _spec_payload(row)
    spec_hash = _hash_spec(payload)
    existing = (
        session.query(SinkVersionRow)
        .filter(
            SinkVersionRow.sink_id == row.id,
            SinkVersionRow.spec_hash == spec_hash,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    version = SinkVersionRow(
        sink_id=row.id,
        version=int(row.current_version or 1),
        spec_hash=spec_hash,
        payload=payload,
        notes=notes,
        created_by=created_by,
        owner_user_id=row.owner_user_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
    )
    session.add(version)
    return version


def create_sink(
    session: Session,
    *,
    name: str,
    kind: str,
    display_name: str | None = None,
    description: str | None = None,
    config: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    documentation_url: str | None = None,
    requires_manifest_node: bool = True,
    enabled: bool = True,
    annotations: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    owner_user_id: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
    created_by: str | None = None,
    notes: str | None = None,
) -> SinkRow:
    """Create a new sink + initial version snapshot."""
    if not name:
        raise SinkValidationError("name is required")
    desc = _validate_kind(kind)
    existing = get_sink_by_name(
        session, name=name, workspace_id=workspace_id, project_id=project_id
    )
    if existing is not None:
        raise SinkValidationError(
            f"sink with name {name!r} already exists in this project"
        )
    row = SinkRow(
        name=name,
        kind=kind,
        display_name=display_name or desc.display_name,
        description=description or desc.description,
        config_json=dict(config or {}),
        tags=list(tags or []),
        documentation_url=documentation_url or desc.documentation_url,
        requires_manifest_node=bool(requires_manifest_node),
        current_version=1,
        enabled=bool(enabled),
        annotations=list(annotations or []),
        meta=dict(meta or {}),
        owner_user_id=owner_user_id,
        workspace_id=workspace_id,
        project_id=project_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(row)
    session.flush()
    _persist_version(session, row, notes=notes, created_by=created_by)
    session.flush()
    return row


def update_sink(
    session: Session,
    sink_id: str,
    *,
    display_name: str | None = None,
    description: str | None = None,
    config: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    documentation_url: str | None = None,
    requires_manifest_node: bool | None = None,
    enabled: bool | None = None,
    annotations: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    notes: str | None = None,
    created_by: str | None = None,
) -> SinkRow:
    """Patch a sink row; bumps version and writes a new snapshot if changed."""
    row = get_sink(session, sink_id)
    pre_payload = _spec_payload(row)
    if display_name is not None:
        row.display_name = display_name
    if description is not None:
        row.description = description
    if config is not None:
        row.config_json = dict(config)
    if tags is not None:
        row.tags = list(tags)
    if documentation_url is not None:
        row.documentation_url = documentation_url
    if requires_manifest_node is not None:
        row.requires_manifest_node = bool(requires_manifest_node)
    if enabled is not None:
        row.enabled = bool(enabled)
    if annotations is not None:
        row.annotations = list(annotations)
    if meta is not None:
        row.meta = dict(meta)
    new_payload = _spec_payload(row)
    if new_payload != pre_payload:
        row.current_version = int(row.current_version or 1) + 1
        row.updated_at = datetime.utcnow()
        _persist_version(session, row, notes=notes, created_by=created_by)
    session.flush()
    return row


def delete_sink(session: Session, sink_id: str) -> None:
    """Soft semantic delete: drop the row + cascading versions."""
    row = get_sink(session, sink_id)
    session.delete(row)
    session.flush()


def materialise_node_spec(
    session: Session,
    sink_id: str,
    *,
    overrides: dict[str, Any] | None = None,
) -> NodeSpec:
    """Resolve a :class:`SinkRow` into a manifest :class:`NodeSpec`.

    Overrides are merged on top of the persisted ``config_json`` so
    callers can patch e.g. ``namespace`` per-run while keeping the
    rest of the registered sink configuration intact.
    """
    row = get_sink(session, sink_id)
    desc = get_sink_descriptor(row.kind)
    template = (
        dict(desc.default_node_template)
        if desc is not None
        else {"name": f"sink.{row.kind}", "kwargs": {}}
    )
    kwargs = {**(template.get("kwargs") or {}), **dict(row.config_json or {})}
    if overrides:
        kwargs.update(overrides)
    name = template.get("name") or f"sink.{row.kind}"
    spec = NodeSpec(
        name=str(name),
        kwargs=kwargs,
        label=row.display_name,
        enabled=bool(row.enabled),
    )
    _emit_sink_lineage(row=row, kwargs=kwargs)
    return spec


def _emit_sink_lineage(*, row: SinkRow, kwargs: dict[str, Any]) -> None:
    """Fire a ``sink`` lineage event when a sink is materialised into a manifest.

    Best-effort: failures are swallowed and logged so callers never see a
    materialise call fail because of a busted lineage table. Tries to
    extract a target Iceberg identifier from the merged kwargs so the
    lineage row points at the table that will be written.
    """
    try:
        from aqp.data.catalog.lineage import LineageEvent, get_lineage_bus

        target = kwargs.get("iceberg_identifier") or kwargs.get("identifier")
        if not target:
            namespace = kwargs.get("namespace")
            table_name = kwargs.get("table") or kwargs.get("table_name") or row.name
            if namespace and table_name:
                target = f"{namespace}.{table_name}"
        get_lineage_bus().emit(
            LineageEvent(
                transform_kind="sink",
                target_table_id=str(target) if target else None,
                actor=f"sink.{row.kind}",
                actor_kind="service",
                service_name=f"sink.{row.kind}",
                summary=f"materialised sink {row.name!r} (kind={row.kind!r})",
                details={
                    "sink_id": row.id,
                    "sink_name": row.name,
                    "sink_kind": row.kind,
                    "current_version": int(row.current_version or 1),
                },
            )
        )
    except Exception:  # noqa: BLE001
        logger.debug("sink lineage emit failed for sink_id=%s", row.id, exc_info=True)


__all__ = [
    "SinkNotFoundError",
    "SinkValidationError",
    "create_sink",
    "delete_sink",
    "get_sink",
    "get_sink_by_name",
    "list_sink_versions",
    "list_sinks",
    "materialise_node_spec",
    "sink_summary",
    "update_sink",
]
