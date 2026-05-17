from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from aqp.data.fabric.identity import FabricHashMixin, FabricIdentity, VersionVector
from aqp.observability.fabric_bus import get_observability_bus

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class VersionConflictError(RuntimeError):
    """Raised when version-vector compatibility check fails and must be surfaced."""


class VersionManager:
    """Manage VersionVector lifecycle for non-spec fabric objects.

    Used by the new tables ``instrument_catalogs``, ``catalog_feed_edges``,
    and ``ingestion_ledger``. Spec versioning
    (agent_spec_versions / bot_versions / rl_experiment_versions /
    analysis_spec_versions / workflow_spec_versions) is intentionally untouched
    because those rows are immutable per AGENTS hard rules 13 / 15 / 17 / 24 / 41.
    """

    def __init__(self, *, session_factory: "Callable[[], Session] | None" = None) -> None:
        if session_factory is None:
            from aqp.persistence.db import get_session as _get_session

            self._session_factory = _get_session
        else:
            self._session_factory = session_factory

    def increment(self, obj: FabricIdentity, *, component: str | None = None) -> VersionVector:
        """Increment ``obj.version_vector`` and re-seal ``obj.content_hash``."""
        comp = component or type(obj).__qualname__
        new_vec = obj.version_vector.incremented(comp)
        obj.version_vector = new_vec
        obj.content_hash = obj.compute_hash()
        return new_vec

    @staticmethod
    def check_compatibility(v1: VersionVector, v2: VersionVector) -> bool:
        """Return True when ``v1`` dominates ``v2`` (no concurrent edit)."""
        return v1.dominates(v2)

    @staticmethod
    def resolve_conflict(v1: VersionVector, v2: VersionVector) -> VersionVector:
        """Merge two vectors via pairwise max and emit a warning."""
        merged = v1.merge(v2)
        get_observability_bus().get_tracer(__name__)
        logger.warning(
            "Version conflict resolved via merge: v1=%s v2=%s -> merged=%s",
            v1.to_dict(),
            v2.to_dict(),
            merged.to_dict(),
        )
        return merged

    def persist_snapshot(
        self,
        obj: FabricIdentity,
        *,
        object_kind: str,
        session: Session | None = None,
    ) -> str:
        """Append a ``FabricVersionSnapshot`` row for the current object state."""
        from aqp.persistence.models_ingestion_ledger import FabricVersionSnapshot

        if isinstance(obj.version_vector, VersionVector):
            version_vector = obj.version_vector.to_dict()
        else:
            version_vector = dict(obj.version_vector or {})

        snapshot = FabricVersionSnapshot(
            id=str(uuid.uuid4()),
            fabric_uuid=str(getattr(obj, "fabric_uuid", "")) or str(uuid.uuid4()),
            object_kind=object_kind,
            version_vector=version_vector,
            snapshot_data=obj.to_canonical_dict(),
            content_hash=obj.compute_hash(),
        )
        if session is not None:
            session.add(snapshot)
            session.flush()
            return str(snapshot.id)

        with self._session_factory() as managed_session:
            managed_session.add(snapshot)
            managed_session.commit()
            return str(snapshot.id)


def verify_lineage_chain(
    fabric_uuid: str | uuid.UUID,
    *,
    session: Session | None = None,
) -> dict[str, Any]:
    """Recompute and verify the FabricVersionSnapshot hash chain for one UUID."""
    fabric_uuid_str = str(fabric_uuid)
    bus = get_observability_bus()
    with bus.record_span(
        "fabric.verify_lineage_chain",
        attributes={"fabric.uuid": fabric_uuid_str},
    ):
        if session is None:
            from aqp.persistence.db import get_session as _get_session

            with _get_session() as managed_session:
                return _verify_with_session(fabric_uuid_str, managed_session)
        return _verify_with_session(fabric_uuid_str, session)


def _verify_with_session(fabric_uuid: str, session: Session) -> dict[str, Any]:
    from aqp.persistence.models_ingestion_ledger import FabricVersionSnapshot
    from aqp.persistence.models_lineage import DataLineageEvent

    rows = (
        session.query(FabricVersionSnapshot)
        .filter(FabricVersionSnapshot.fabric_uuid == fabric_uuid)
        .order_by(FabricVersionSnapshot.created_at.asc())
        .all()
    )
    mismatches: list[dict[str, Any]] = []
    for row in rows:
        snapshot_data = row.snapshot_data if isinstance(row.snapshot_data, dict) else {}
        recomputed = FabricHashMixin.compute_dict_hash(snapshot_data)
        if recomputed != row.content_hash:
            logger.critical(
                "Fabric lineage hash mismatch: fabric_uuid=%s snapshot_id=%s stored=%s computed=%s",
                fabric_uuid,
                row.id,
                row.content_hash,
                recomputed,
            )
            mismatches.append(
                {
                    "snapshot_id": str(row.id),
                    "stored_hash": row.content_hash,
                    "computed_hash": recomputed,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )

    lineage_count = (
        session.query(DataLineageEvent)
        .filter(
            (DataLineageEvent.source_table_id == fabric_uuid)
            | (DataLineageEvent.target_table_id == fabric_uuid)
            | (DataLineageEvent.run_id == fabric_uuid)
            | (DataLineageEvent.manifest_id == fabric_uuid)
        )
        .count()
    )

    return {
        "fabric_uuid": fabric_uuid,
        "ok": len(mismatches) == 0,
        "checked": len(rows),
        "mismatches": mismatches,
        "lineage_events": int(lineage_count),
    }


__all__ = [
    "VersionConflictError",
    "VersionManager",
    "verify_lineage_chain",
]
