"""Lineage inspection routes for Data Fabric Phase 4."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from aqp.api.security import require_authenticated
from aqp.persistence.db import get_session
from aqp.persistence.models_ingestion_ledger import (
    FabricVersionSnapshot,
    IngestionLedgerRow,
)
from aqp.persistence.models_lineage import DataLineageEvent

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["lineage"],
    dependencies=[Depends(require_authenticated)],
)


def _fallback_lineage_events(*, fabric_uuid: str, session: Any) -> list[dict[str, Any]]:
    rows = (
        session.query(DataLineageEvent)
        .filter(
            (DataLineageEvent.source_table_id == fabric_uuid)
            | (DataLineageEvent.target_table_id == fabric_uuid)
            | (DataLineageEvent.run_id == fabric_uuid)
            | (DataLineageEvent.manifest_id == fabric_uuid)
        )
        .order_by(DataLineageEvent.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "transform_kind": str(row.transform_kind),
            "source_table_id": row.source_table_id,
            "target_table_id": row.target_table_id,
            "actor": row.actor,
            "summary": row.summary,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/object/{fabric_uuid}")
def lineage_for_object(fabric_uuid: str) -> dict[str, Any]:
    with get_session() as session:
        try:
            from aqp.data.fabric.versioning import verify_lineage_chain
        except ImportError:
            logger.warning(
                "verify_lineage_chain unavailable; returning degraded lineage payload"
            )
            snapshots = (
                session.query(FabricVersionSnapshot)
                .filter(FabricVersionSnapshot.fabric_uuid == str(fabric_uuid))
                .order_by(FabricVersionSnapshot.created_at.asc())
                .all()
            )
            return {
                "fabric_uuid": str(fabric_uuid),
                "ok": None,
                "snapshots": [
                    {
                        "id": str(row.id),
                        "object_kind": str(row.object_kind),
                        "version_vector": dict(row.version_vector or {}),
                        "content_hash": str(row.content_hash),
                        "created_at": row.created_at.isoformat()
                        if row.created_at
                        else None,
                    }
                    for row in snapshots
                ],
                "lineage_events": _fallback_lineage_events(
                    fabric_uuid=str(fabric_uuid),
                    session=session,
                ),
            }
        return verify_lineage_chain(str(fabric_uuid), session=session)


@router.get("/ledger/{ledger_uuid}")
def lineage_for_ledger(ledger_uuid: str) -> dict[str, Any]:
    with get_session() as session:
        row = (
            session.query(IngestionLedgerRow)
            .filter(IngestionLedgerRow.id == str(ledger_uuid))
            .one_or_none()
        )
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"ledger {ledger_uuid} not found",
            )
        return {
            "ledger_uuid": str(ledger_uuid),
            "fabric_uuid": str(row.fabric_uuid),
            "request_hash": str(row.request_hash),
            "lineage_snapshot": dict(row.lineage_snapshot or {}),
            "execution_start": row.execution_start.isoformat()
            if row.execution_start
            else None,
            "execution_end": row.execution_end.isoformat() if row.execution_end else None,
            "status": str(row.execution_status),
        }


__all__ = ["router"]
