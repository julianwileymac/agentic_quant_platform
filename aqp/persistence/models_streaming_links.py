"""Streaming-component <-> dataset linkage table.

Lets a dataset be queried for "which Kafka topics feed me, which
Flink jobs read me, which dbt models derive from me, which Airbyte
connection produced me, which Dagster asset materialized me, and
which producer is upstream".

The same row stores either inbound or outbound relationships via the
``direction`` column (``source`` / ``sink`` / ``bidirectional``). The
``kind`` discriminator selects the streaming-component subspace and
``target_ref`` is the human-readable identifier (topic name,
session-job name, connection id, model unique_id, asset key, or
producer name).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class StreamingDatasetLink(Base, ProjectScopedMixin):
    """Many-to-many link between a dataset catalog and a streaming component."""

    __tablename__ = "streaming_dataset_links"

    id = Column(String(36), primary_key=True, default=_uuid)
    dataset_catalog_id = Column(
        String(36),
        ForeignKey("dataset_catalogs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    dataset_namespace = Column(String(120), nullable=True, index=True)
    dataset_table = Column(String(240), nullable=True, index=True)
    kind = Column(String(40), nullable=False, default="kafka_topic", index=True)
    # kafka_topic | flink_job | airbyte_connection | dbt_model |
    # dagster_asset | producer | sink
    target_ref = Column(String(512), nullable=False, index=True)
    cluster_ref = Column(String(240), nullable=True, index=True)
    direction = Column(
        String(20), nullable=False, default="source", index=True
    )
    # source | sink | bidirectional
    metadata_json = Column(JSON, default=dict)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    discovered_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "dataset_catalog_id",
            "kind",
            "target_ref",
            "direction",
            name="uq_streaming_dataset_links_natural",
        ),
    )


Index(
    "ix_streaming_dataset_links_lookup",
    StreamingDatasetLink.kind,
    StreamingDatasetLink.target_ref,
)


__all__ = ["StreamingDatasetLink"]
