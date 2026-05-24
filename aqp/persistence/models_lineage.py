"""First-class data lineage events.

Stores one row per material data motion (Iceberg append, sink
materialise, dbt build, Airbyte sync, MCP tool invocation, streaming
flow). Replaces the opaque ``PipelineRunRow.lineage`` JSON blob with a
queryable graph that the Data Hub UI and the DataMCP tools can walk.

The :class:`aqp.data.catalog.lineage.LineageWriter` is the single sync
entry point — never write directly to ``data_lineage_events`` from
business code. Observers under
:mod:`aqp.data.catalog.lineage` decide which events fire from which
spots in the pipeline so the rule "all writes to this table go through
``LineageWriter``" stays enforceable.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    String,
    Text,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ``transform_kind`` is intentionally a free-form string so new motion
# kinds (e.g. dbt-streaming, ksql, vbtpro paper-replay) can be added
# without an Alembic migration. The canonical values are documented in
# ``aqp_docs/data-products.md``.
LINEAGE_TRANSFORM_KINDS = (
    "iceberg_append",
    "iceberg_create_or_replace",
    "iceberg_time_travel_read",
    "materialize",
    "sink",
    "dbt",
    "airbyte",
    "streaming_kafka",
    "streaming_flink",
    "mcp_tool",
    "schema_drift",
    "datahub_emit",
    "datahub_pull",
)


class DataLineageEvent(Base, ProjectScopedMixin):
    """One material data-motion event.

    The pair (``source_table_id``, ``target_table_id``) describes a
    directed edge in the lineage graph. Either side can be ``None``
    (source-only writes such as ``iceberg_append`` from a materialise
    job have no upstream Iceberg table; pure reads have no downstream
    target).
    """

    __tablename__ = "data_lineage_events"

    id = Column(String(36), primary_key=True, default=_uuid)

    # Edge endpoints — Iceberg ``namespace.table`` identifiers. Free-form
    # strings so we can record events for tables that aren't yet in the
    # ``DatasetCatalog`` ORM (eg. raw bronze landings).
    source_table_id = Column(String(240), nullable=True, index=True)
    target_table_id = Column(String(240), nullable=True, index=True)

    transform_kind = Column(String(40), nullable=False, index=True)
    actor = Column(String(120), nullable=True, index=True)
    actor_kind = Column(String(32), nullable=True)  # user|agent|service|system

    # Optional links into existing pipeline state. ORM does not declare
    # ``ForeignKey`` constraints because lineage events also fire from
    # places that have no manifest/run (eg. an ad-hoc agent tool call).
    run_id = Column(String(36), nullable=True, index=True)
    manifest_id = Column(String(36), nullable=True, index=True)
    mcp_tool_name = Column(String(120), nullable=True, index=True)
    service_name = Column(String(120), nullable=True, index=True)

    rows_written = Column(String(32), nullable=True)  # stringified to keep big counts JSON-safe
    medallion_layer = Column(String(16), nullable=True, index=True)
    summary = Column(Text, nullable=True)
    details_json = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_lineage_source_target", "source_table_id", "target_table_id"),
        Index("ix_lineage_kind_created", "transform_kind", "created_at"),
        Index("ix_lineage_actor", "actor", "actor_kind"),
    )


__all__ = ["DataLineageEvent", "LINEAGE_TRANSFORM_KINDS"]
