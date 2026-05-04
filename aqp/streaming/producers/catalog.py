"""Curated producer catalog for first-time bootstrap.

Each entry corresponds to a known Kafka-bound producer the platform
ships with — Alpha-Vantage REST poller, IBKR / Alpaca live ingesters,
Polygon, and the synthetic sample producer. The
:class:`ProducerSupervisor` seeds these into the
``market_data_producers`` table the first time it boots so the UI
has something to render before users register custom rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProducerSpec:
    name: str
    kind: str
    runtime: str  # kubernetes | local | cluster_proxy
    display_name: str
    description: str
    deployment_namespace: str | None = None
    deployment_name: str | None = None
    image: str | None = None
    topics: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    desired_replicas: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "runtime": self.runtime,
            "display_name": self.display_name,
            "description": self.description,
            "deployment_namespace": self.deployment_namespace,
            "deployment_name": self.deployment_name,
            "image": self.image,
            "topics": list(self.topics),
            "config": dict(self.config),
            "desired_replicas": int(self.desired_replicas),
            "tags": list(self.tags),
        }


PRODUCER_CATALOG: tuple[ProducerSpec, ...] = (
    ProducerSpec(
        name="alphavantage",
        kind="alphavantage",
        runtime="cluster_proxy",
        display_name="Alpha Vantage Producer",
        description=(
            "REST poller scaled by the rpi_kubernetes management API "
            "(POST /api/alphavantage/stream)."
        ),
        deployment_namespace="data-services",
        deployment_name="alphavantage-producer",
        image="ghcr.io/julianwiley/alphavantage-producer:0.1.0",
        topics=[
            "alphavantage.intraday.v1",
            "alphavantage.daily.v1",
            "alphavantage.fundamentals.v1",
        ],
        config={"toggle_endpoint": "/alphavantage/stream"},
        tags=["rest", "polling"],
    ),
    ProducerSpec(
        name="ibkr",
        kind="ibkr",
        runtime="kubernetes",
        display_name="IBKR Live Ingester",
        description=(
            "ib_async-based live ingester. Connects to TWS/Gateway and "
            "streams quotes/trades into market.* topics."
        ),
        deployment_namespace="data-services",
        deployment_name="aqp-ingester-ibkr",
        image="ghcr.io/julianwiley/aqp-stream-ingest:latest",
        topics=["market.quote.v1", "market.trade.v1", "market.bar.v1"],
        config={"venue": "ibkr"},
        tags=["live", "ibkr"],
    ),
    ProducerSpec(
        name="alpaca",
        kind="alpaca",
        runtime="kubernetes",
        display_name="Alpaca Live Ingester",
        description=(
            "WebSocket ingester for Alpaca market-data streams. Powers "
            "intraday backtests + paper trading."
        ),
        deployment_namespace="data-services",
        deployment_name="aqp-ingester-alpaca",
        image="ghcr.io/julianwiley/aqp-stream-ingest:latest",
        topics=["market.quote.v1", "market.trade.v1", "market.bar.v1"],
        config={"venue": "alpaca"},
        tags=["live", "alpaca"],
    ),
    ProducerSpec(
        name="polygon",
        kind="polygon",
        runtime="kubernetes",
        display_name="Polygon WebSocket Producer",
        description="Polygon.io WebSocket producer for US equities / options.",
        deployment_namespace="data-services",
        deployment_name="polygon-producer",
        topics=["market.quote.v1", "market.trade.v1"],
        config={"venue": "polygon"},
        tags=["live", "polygon"],
    ),
    ProducerSpec(
        name="synthetic",
        kind="synthetic",
        runtime="kubernetes",
        display_name="Synthetic Producer",
        description="Deterministic synthetic ticks for end-to-end tests.",
        deployment_namespace="data-services",
        deployment_name="synthetic-producer-sample",
        topics=["market.synthetic.v1"],
        config={"seed": 42},
        desired_replicas=1,
        tags=["sample", "synthetic"],
    ),
)


def list_producer_specs() -> list[ProducerSpec]:
    return list(PRODUCER_CATALOG)


__all__ = ["PRODUCER_CATALOG", "ProducerSpec", "list_producer_specs"]
