"""Bipartite lineage DAG ORM (Workstream A).

The platform already has a flat ``data_lineage_events`` edge-log table
(see :mod:`aqp.persistence.models_lineage`). Workstream A adds a
first-class bipartite DAG on top:

- :class:`DatasetVertex` — one row per content-addressed dataset
  snapshot (Iceberg manifest + snapshot id, or any other immutable
  artifact identifier).
- :class:`TransformVertex` — one row per data motion (Iceberg append,
  MCP tool call, materialise step, dbt build, etc.).
- :class:`LineageEdge` — directed edge between vertices. ``edge_type``
  is ``consumes`` (dataset -> transform) or ``produces`` (transform ->
  dataset).

The flat ``data_lineage_events`` log keeps writing unchanged — the
new tables are a purely additive consumer of the same
:class:`LineageBus`. Operators flip ``AQP_LINEAGE_GRAPH_ENABLED=true``
to activate dual-write.

All three tables sit alongside the existing tenancy mixins
(``owner_user_id`` / ``workspace_id`` / ``project_id``) so per-org
filtering matches the rest of the platform. Signature columns on
:class:`TransformVertex` are populated by :mod:`aqp.auth.signing`
(workstream C); they remain nullable so deployments that opt out of
signing still get usable graph rows.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DatasetVertex(Base, ProjectScopedMixin):
    """One row per content-addressed dataset snapshot.

    ``content_hash`` is the SHA-256 of the snapshot identifier:

    - For Iceberg-backed datasets it is SHA-256 of the manifest-list
      location string concatenated with the integer ``snapshot_id``
      (the snapshot manifest IS Iceberg's native content-address; we
      surface a stable digest so non-Iceberg datasets share the same
      column shape).
    - For Parquet / file-system datasets it is SHA-256 over the file
      bytes (or the directory listing for partitioned datasets).
    - For external datasets it is SHA-256 over the canonical URI +
      version string.

    The same logical dataset can have many ``DatasetVertex`` rows over
    its lifetime, one per snapshot. The
    ``(namespace, name, content_hash)`` triple is unique.
    """

    __tablename__ = "lineage_dataset_vertex"

    id = Column(String(36), primary_key=True, default=_uuid)
    namespace = Column(String(120), nullable=False, index=True)
    name = Column(String(240), nullable=False, index=True)
    content_hash = Column(String(64), nullable=False, index=True)

    # Iceberg-specific fields. Nullable for non-Iceberg datasets.
    iceberg_snapshot_id = Column(BigInteger, nullable=True, index=True)
    manifest_list_location = Column(Text, nullable=True)

    schema_facet = Column(JSON, default=dict)
    row_count = Column(BigInteger, nullable=True)
    byte_size = Column(BigInteger, nullable=True)
    medallion_layer = Column(String(16), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    # Phase 7 §10.3 (Alembic 0086) — cell-aware lineage.
    cell_id = Column(String(120), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint(
            "namespace", "name", "content_hash", name="uq_lineage_dataset_vertex_addr"
        ),
        Index("ix_lineage_dataset_vertex_ns_name", "namespace", "name"),
    )


class TransformVertex(Base, ProjectScopedMixin):
    """One row per data motion.

    ``job_name`` is the canonical transform identifier — typically a
    :class:`LineageEvent.transform_kind` plus a stable handle (e.g.
    ``"iceberg_append:aqp_silver_equities_bars"``). ``run_id`` ties the
    vertex to the originating Celery / pipeline run when known.

    Signature columns are populated by
    :func:`aqp.auth.signing.sign_transform_payload` when
    ``AQP_LINEAGE_SIGNING_ENABLED=true``. They stay nullable so
    deployments that opt out of signing still get full lineage; auditors
    can identify unsigned rows by ``signing_key_id IS NULL`` or
    ``signing_key_id = 'null'``.
    """

    __tablename__ = "lineage_transform_vertex"

    id = Column(String(36), primary_key=True, default=_uuid)
    job_name = Column(String(240), nullable=False, index=True)
    run_id = Column(String(36), nullable=True, index=True)
    code_version = Column(String(120), nullable=True)
    transform_kind = Column(String(40), nullable=False, index=True)

    parameters = Column(JSON, default=dict)
    actor = Column(String(120), nullable=True, index=True)
    actor_kind = Column(String(32), nullable=True)
    service_name = Column(String(120), nullable=True)
    mcp_tool_name = Column(String(120), nullable=True, index=True)

    rows_written = Column(BigInteger, nullable=True)
    summary = Column(Text, nullable=True)

    # Signature columns (workstream C). Nullable when signing is off.
    signature = Column(Text, nullable=True)
    signing_key_id = Column(String(96), nullable=True, index=True)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True)
    # Phase 7 §10.3 (Alembic 0086) — cell-aware lineage.
    cell_id = Column(String(120), nullable=True, index=True)

    __table_args__ = (
        Index("ix_lineage_transform_vertex_kind_started", "transform_kind", "started_at"),
        Index("ix_lineage_transform_vertex_actor", "actor", "actor_kind"),
    )


class LineageEdge(Base, ProjectScopedMixin):
    """Directed edge between vertices.

    ``edge_type``:

    - ``"consumes"`` — ``from_vertex`` is a :class:`DatasetVertex`,
      ``to_vertex`` is a :class:`TransformVertex`.
    - ``"produces"`` — ``from_vertex`` is a :class:`TransformVertex`,
      ``to_vertex`` is a :class:`DatasetVertex`.

    The bipartite structure is enforced at the writer level (see
    :class:`aqp.lineage.graph.writer.LineageGraphWriter`) rather than
    via a CHECK constraint so the same table can carry both edge
    directions without DB-specific bipartite enforcement.
    """

    __tablename__ = "lineage_edge"

    id = Column(String(36), primary_key=True, default=_uuid)
    from_vertex = Column(String(36), nullable=False, index=True)
    to_vertex = Column(String(36), nullable=False, index=True)
    edge_type = Column(String(16), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    # Phase 7 §10.3 (Alembic 0086) — cell-aware lineage.
    cell_id = Column(String(120), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint(
            "from_vertex", "to_vertex", "edge_type", name="uq_lineage_edge_triple"
        ),
        Index("ix_lineage_edge_to_from", "to_vertex", "from_vertex"),
    )


__all__ = ["DatasetVertex", "LineageEdge", "TransformVertex"]
