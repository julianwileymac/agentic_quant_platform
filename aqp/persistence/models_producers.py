"""Market-data producer registry.

Tracks every "lightweight producer" component that pushes records
into Kafka topics for the AQP streaming layer. Examples: the
``alphavantage-producer`` Deployment in the rpi_kubernetes cluster,
the local ``aqp-stream-ingest`` IBKR/Alpaca ingesters, and any
custom synthetic / polygon producer.

A producer row is **the control-plane handle** the
:class:`aqp.streaming.producers.supervisor.ProducerSupervisor` uses
to start/stop/scale the underlying workload (k8s Deployment scale
patch, local subprocess, or cluster-mgmt Alpha-Vantage stream toggle).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MarketDataProducerRow(Base, ProjectScopedMixin):
    """One Kafka-bound market-data producer (k8s Deployment or local CLI)."""

    __tablename__ = "market_data_producers"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(180), nullable=False, index=True)
    kind = Column(String(40), nullable=False, default="alphavantage", index=True)
    # alphavantage | ibkr | alpaca | polygon | synthetic | custom
    runtime = Column(String(40), nullable=False, default="kubernetes", index=True)
    # kubernetes | local | cluster_proxy
    display_name = Column(String(240), nullable=False)
    description = Column(Text, nullable=True)
    deployment_namespace = Column(String(120), nullable=True, index=True)
    deployment_name = Column(String(180), nullable=True, index=True)
    image = Column(String(512), nullable=True)
    topics = Column(JSON, default=list)
    config_json = Column(JSON, default=dict)
    env_overrides = Column(JSON, default=dict)
    desired_replicas = Column(Integer, nullable=False, default=0)
    current_replicas = Column(Integer, nullable=False, default=0)
    last_status = Column(String(40), nullable=False, default="unknown", index=True)
    last_status_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    tags = Column(JSON, default=list)
    annotations = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_market_producers_project_name"),
    )


Index(
    "ix_market_data_producers_kind_status",
    MarketDataProducerRow.kind,
    MarketDataProducerRow.last_status,
)


__all__ = ["MarketDataProducerRow"]
