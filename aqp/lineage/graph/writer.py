"""Single sanctioned writer for the bipartite lineage graph (Workstream A).

The graph has three tables: :class:`DatasetVertex`,
:class:`TransformVertex`, :class:`LineageEdge`. The writer below is
the only path that should insert rows — observers and MCP tools call
through it so:

- Content-address-based deduplication actually deduplicates
  (idempotent re-emission produces the same row).
- Ed25519 signing (workstream C) happens once, in one place.
- Tenancy stamping reuses :class:`LedgerWriter` semantics implicitly
  by reading :class:`RequestContext` from the contextvar.

Failures are swallowed and logged — lineage is a side channel; a busted
graph insert MUST NOT block the data path.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from typing import Any

from aqp.auth.signing import ActorIdentity, sign_transform_payload
from aqp.lineage.graph.content_address import (
    fallback_content_hash,
    iceberg_snapshot_address,
)
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)


_ICEBERG_TRANSFORM_KINDS = frozenset(
    {
        "iceberg_append",
        "iceberg_create_or_replace",
        "iceberg_time_travel_read",
    }
)


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class LineageGraphWriter:
    """Append-only writer for the bipartite lineage tables.

    Public surface:

    - :meth:`record_event(event)` — translate a
      :class:`aqp.data.catalog.lineage.LineageEvent` into the
      corresponding ``(transform_vertex, edges, optional
      dataset_vertex)`` tuple and persist it idempotently.
    - :meth:`upsert_dataset_vertex(...)` — explicit dataset vertex
      upsert, used by callers that already know the content address.
    - :meth:`suppress()` — class-level contextmanager mirroring
      :class:`aqp.data.catalog.lineage.LineageWriter.suppress`. Tests
      use it to keep the graph silent during fixture setup.
    """

    _suppression_depth = threading.local()

    def record_event(self, event: Any) -> str | None:
        """Persist the graph rows implied by a :class:`LineageEvent`.

        Returns the new :class:`TransformVertex.id` on success or
        ``None`` when the writer is suppressed or the insert fails.
        """
        if getattr(self._suppression_depth, "value", 0) > 0:
            return None
        try:
            return self._record_event_inner(event)
        except Exception:  # noqa: BLE001
            logger.exception(
                "LineageGraphWriter.record_event failed for kind=%s target=%s",
                getattr(event, "transform_kind", "?"),
                getattr(event, "target_table_id", "?"),
            )
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_event_inner(self, event: Any) -> str | None:
        from aqp.persistence.models_lineage_graph import (
            DatasetVertex,
            LineageEdge,
            TransformVertex,
        )

        transform_kind = str(getattr(event, "transform_kind", "") or "unknown")
        details = dict(getattr(event, "details", {}) or {})

        with get_session() as session:
            # Resolve OR create the upstream (source) dataset vertex
            # when the event names a source table. The same applies on
            # the downstream side for the produced dataset.
            source_id = getattr(event, "source_table_id", None)
            target_id = getattr(event, "target_table_id", None)

            source_vertex: DatasetVertex | None = None
            if source_id:
                source_vertex = self._resolve_dataset_vertex(
                    session,
                    table_identifier=str(source_id),
                    transform_kind=transform_kind,
                    medallion_layer=getattr(event, "medallion_layer", None),
                    details=details,
                )

            target_vertex: DatasetVertex | None = None
            if target_id:
                target_vertex = self._resolve_dataset_vertex(
                    session,
                    table_identifier=str(target_id),
                    transform_kind=transform_kind,
                    medallion_layer=getattr(event, "medallion_layer", None),
                    details=details,
                    row_count=getattr(event, "rows_written", None),
                )

            # Build the transform vertex.
            run_id = getattr(event, "run_id", None)
            actor = getattr(event, "actor", None) or "unknown"
            actor_kind = getattr(event, "actor_kind", None) or "service"
            mcp_tool_name = getattr(event, "mcp_tool_name", None)
            service_name = getattr(event, "service_name", None)
            manifest_id = getattr(event, "manifest_id", None)

            transform_handle = target_id or source_id or transform_kind
            job_name = f"{transform_kind}:{transform_handle}" if transform_handle else transform_kind
            code_version = str(details.get("code_version") or "")
            parameters = dict(details.get("parameters") or {})
            if not parameters and manifest_id:
                parameters = {"manifest_id": str(manifest_id)}

            # Workstream C signing: best-effort. The signer no-ops when
            # signing is off; otherwise it sha256-hashes the canonical
            # encoding and Ed25519-signs it. The two columns end up
            # null / ``"null"`` in off mode, real values in on mode.
            input_hashes = [source_vertex.content_hash] if source_vertex is not None else []
            output_hashes = [target_vertex.content_hash] if target_vertex is not None else []
            signature, signing_key_id = sign_transform_payload(
                actor=ActorIdentity(kind=str(actor_kind), ref=str(actor)),
                job_name=job_name,
                run_id=str(run_id) if run_id else "",
                code_version=code_version,
                parameters=parameters,
                input_hashes=input_hashes,
                output_hashes=output_hashes,
            )

            transform = TransformVertex(
                id=_new_id(),
                job_name=job_name,
                run_id=str(run_id) if run_id else None,
                code_version=code_version or None,
                transform_kind=transform_kind,
                parameters=parameters,
                actor=str(actor)[:120] if actor else None,
                actor_kind=str(actor_kind)[:32] if actor_kind else None,
                service_name=str(service_name)[:120] if service_name else None,
                mcp_tool_name=str(mcp_tool_name)[:120] if mcp_tool_name else None,
                rows_written=int(getattr(event, "rows_written", 0) or 0) or None,
                summary=getattr(event, "summary", None),
                signature=signature or None,
                signing_key_id=signing_key_id or None,
                started_at=datetime.utcnow(),
            )
            _stamp_tenancy(transform, event)
            session.add(transform)
            session.flush()

            edges: list[LineageEdge] = []
            if source_vertex is not None:
                edges.append(self._make_edge(source_vertex.id, transform.id, "consumes", event))
            if target_vertex is not None:
                edges.append(self._make_edge(transform.id, target_vertex.id, "produces", event))

            for edge in edges:
                session.merge(edge)  # merge to honour unique constraint idempotently

            session.commit()
            return str(transform.id)

    def _resolve_dataset_vertex(
        self,
        session: Any,
        *,
        table_identifier: str,
        transform_kind: str,
        medallion_layer: str | None,
        details: dict[str, Any],
        row_count: int | None = None,
    ) -> Any:
        """Find-or-create a :class:`DatasetVertex` for ``table_identifier``.

        For Iceberg-backed identifiers we compute the snapshot
        content-address. For everything else we fall back to a hash of
        ``(table_identifier || transform_kind || details_summary)``.
        """
        from aqp.persistence.models_lineage_graph import DatasetVertex

        namespace, name = _split_identifier(table_identifier)
        snapshot_id: int | None = None
        manifest_list_location: str | None = None
        is_iceberg = transform_kind in _ICEBERG_TRANSFORM_KINDS or table_identifier.startswith("aqp_")

        if is_iceberg:
            address = iceberg_snapshot_address(table_identifier)
            content_hash = address.content_hash or fallback_content_hash(table_identifier, transform_kind)
            snapshot_id = address.snapshot_id
            manifest_list_location = address.manifest_list_location
        else:
            content_hash = fallback_content_hash(
                table_identifier,
                transform_kind,
                details.get("manifest_id"),
                details.get("snapshot_id"),
            )

        existing = (
            session.query(DatasetVertex)
            .filter(
                DatasetVertex.namespace == namespace,
                DatasetVertex.name == name,
                DatasetVertex.content_hash == content_hash,
            )
            .one_or_none()
        )
        if existing is not None:
            return existing

        vertex = DatasetVertex(
            id=_new_id(),
            namespace=namespace,
            name=name,
            content_hash=content_hash,
            iceberg_snapshot_id=snapshot_id,
            manifest_list_location=manifest_list_location,
            medallion_layer=medallion_layer,
            row_count=int(row_count) if row_count else None,
            schema_facet={},
        )
        session.add(vertex)
        session.flush()
        return vertex

    def _make_edge(
        self,
        from_vertex: str,
        to_vertex: str,
        edge_type: str,
        event: Any,
    ) -> Any:
        from aqp.persistence.models_lineage_graph import LineageEdge

        edge = LineageEdge(
            id=_new_id(),
            from_vertex=from_vertex,
            to_vertex=to_vertex,
            edge_type=edge_type,
            created_at=datetime.utcnow(),
        )
        _stamp_tenancy(edge, event)
        return edge

    # ------------------------------------------------------------------
    # Suppression
    # ------------------------------------------------------------------

    @classmethod
    def suppress_block(cls) -> "_GraphSuppressionContext":
        return _GraphSuppressionContext(cls._suppression_depth)


class _GraphSuppressionContext:
    def __init__(self, local: threading.local) -> None:
        self._local = local

    def __enter__(self) -> None:
        depth = getattr(self._local, "value", 0)
        self._local.value = depth + 1

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        depth = getattr(self._local, "value", 1)
        self._local.value = max(0, depth - 1)


_default_writer: LineageGraphWriter | None = None
_default_writer_lock = threading.RLock()


def get_default_graph_writer() -> LineageGraphWriter:
    """Process-wide singleton :class:`LineageGraphWriter`."""
    global _default_writer
    if _default_writer is None:
        with _default_writer_lock:
            if _default_writer is None:
                _default_writer = LineageGraphWriter()
    return _default_writer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_identifier(table_id: str) -> tuple[str, str]:
    """Split ``"namespace.table"`` into a ``(namespace, name)`` tuple.

    Handles Iceberg-style ``"aqp_bronze_foo.bar.baz"`` by taking the
    first segment as the namespace and joining the rest as the name.
    """
    raw = str(table_id or "").strip()
    if not raw:
        return ("", "")
    parts = raw.split(".", 1)
    if len(parts) == 1:
        return ("", parts[0])
    return (parts[0], parts[1])


def _stamp_tenancy(row: Any, event: Any) -> None:
    """Copy tenancy fields from ``event`` to the new ``row``.

    Mirrors the tenancy stamping in
    :mod:`aqp.persistence.ledger`. We duck-type on the event so the
    same writer accepts both :class:`LineageEvent` (which has these
    fields) and other lightweight shapes.
    """
    for field in ("owner_user_id", "workspace_id", "project_id"):
        value = getattr(event, field, None)
        if value and hasattr(row, field) and getattr(row, field, None) in (None, ""):
            setattr(row, field, value)


__all__ = [
    "LineageGraphWriter",
    "get_default_graph_writer",
]
