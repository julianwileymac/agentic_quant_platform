"""Lightweight market-data producer control plane.

Each :class:`aqp.persistence.MarketDataProducerRow` is the AQP-side
handle to a Kafka-bound producer (Alpha-Vantage REST poller, IBKR
ingester, Alpaca ingester, custom synthetic / polygon producer).
The :class:`ProducerSupervisor` exposes a uniform start / stop /
scale / status / logs surface that delegates to:

- :class:`aqp.services.cluster_mgmt_client.ClusterMgmtClient` for
  kubernetes-backed producers (default path).
- A local subprocess wrapper around ``aqp-stream-ingest`` for
  development on a workstation without a cluster.
"""
from aqp.streaming.producers.catalog import (
    PRODUCER_CATALOG,
    ProducerSpec,
    list_producer_specs,
)
from aqp.streaming.producers.supervisor import (
    ProducerError,
    ProducerSupervisor,
    get_supervisor,
)

__all__ = [
    "PRODUCER_CATALOG",
    "ProducerError",
    "ProducerSpec",
    "ProducerSupervisor",
    "get_supervisor",
    "list_producer_specs",
]
