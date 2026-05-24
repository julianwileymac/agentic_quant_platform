"""Topic-prefix registry for the side-by-side Strimzi + Redpanda topology.

Phase 2a of the AQP infra-expansion plan introduces Redpanda alongside
the existing Strimzi Kafka cluster (per plan question 2 -
``side_by_side``). To keep the existing call sites working, this
module:

1. Exposes a :class:`StreamingCluster` dataclass that captures the
   bootstrap server, schema registry URL, and security configuration
   for one cluster.
2. Maintains a :data:`CLUSTER_REGISTRY` keyed by cluster alias
   (``"strimzi"``, ``"redpanda"``) backed by ``aqp.config.settings``.
3. Implements :func:`cluster_for_topic` which walks
   :data:`TOPIC_PREFIX_ROUTES` to assign a topic to the correct
   cluster based on its name prefix:

   * ``market.l1.*`` -> Redpanda (low-latency Level 1 tick data)
   * ``market.l2.*`` -> Redpanda (Level 2 order-book updates)
   * ``execution.orders.*`` -> Redpanda (broker execution signals)
   * ``agentic.state.*`` -> Redpanda (agent reasoning state)
   * everything else -> Strimzi (existing factor / Avro / DataHub /
     RAG / etc. topics)

The plan explicitly forbids changing the Iceberg single-write-path
(rule 3); analogously, all admin / producer call sites continue to
default to Strimzi unless the topic prefix matches a Redpanda route
or an explicit ``cluster=...`` kwarg is passed. Existing routes,
tasks, and DataMCP tools keep their behavior; new market-data /
execution flows automatically pick up Redpanda once their topic
names land.

Topology resolution: when ``settings.redpanda_bootstrap`` is empty
(local dev, sandbox), :func:`get_cluster("redpanda")` falls back to
the Strimzi cluster so existing code keeps working without a
Redpanda deployment available. ``aqp_control_plane``-side admin
endpoints (``/manage/streaming/{cluster}``) consume this registry
through :func:`list_clusters`.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Iterable

from aqp.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamingCluster:
    """Immutable descriptor for a Kafka-protocol streaming cluster.

    The producer / admin facades resolve their wire-level
    configuration through this dataclass instead of reading
    ``settings.kafka_*`` directly so the Strimzi -> Redpanda routing
    decision is made in exactly one place.
    """

    name: str
    bootstrap: str
    admin_bootstrap: str
    schema_registry_url: str
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str = ""
    sasl_username: str = ""
    sasl_password: str = ""
    label: str = ""
    namespace: str = ""

    def admin_config(self) -> dict[str, Any]:
        """Return a confluent-kafka-py ``AdminClient`` config dict."""
        cfg: dict[str, Any] = {
            "bootstrap.servers": self.admin_bootstrap or self.bootstrap,
            "client.id": f"aqp-admin-{self.name}",
        }
        if self.security_protocol and self.security_protocol != "PLAINTEXT":
            cfg["security.protocol"] = self.security_protocol
        if self.sasl_mechanism:
            cfg["sasl.mechanism"] = self.sasl_mechanism
        if self.sasl_username:
            cfg["sasl.username"] = self.sasl_username
        if self.sasl_password:
            cfg["sasl.password"] = self.sasl_password
        return cfg

    def producer_config(self, *, client_id: str | None = None) -> dict[str, Any]:
        """Return a confluent-kafka-py ``Producer`` config dict (without
        compression / acks / linger knobs - the producer adds those)."""
        cfg: dict[str, Any] = {
            "bootstrap.servers": self.bootstrap,
            "client.id": client_id or f"aqp-{self.name}",
        }
        if self.security_protocol and self.security_protocol != "PLAINTEXT":
            cfg["security.protocol"] = self.security_protocol
        if self.sasl_mechanism:
            cfg["sasl.mechanism"] = self.sasl_mechanism
        if self.sasl_username:
            cfg["sasl.username"] = self.sasl_username
        if self.sasl_password:
            cfg["sasl.password"] = self.sasl_password
        return cfg


# Topic-prefix routes. A topic is assigned to the FIRST cluster whose
# prefix list contains a string that the topic name starts with. New
# prefixes are added here; everything not matched falls through to the
# default cluster (Strimzi).
TOPIC_PREFIX_ROUTES: tuple[tuple[str, str], ...] = (
    ("redpanda", "market.l1."),
    ("redpanda", "market.l2."),
    ("redpanda", "execution.orders."),
    ("redpanda", "agentic.state."),
)

DEFAULT_CLUSTER = "strimzi"


_LOCK = threading.RLock()
_CACHE: dict[str, StreamingCluster] | None = None


def _build_strimzi_cluster() -> StreamingCluster:
    """Build the Strimzi cluster descriptor from legacy ``kafka_*`` settings."""
    return StreamingCluster(
        name="strimzi",
        bootstrap=settings.kafka_bootstrap,
        admin_bootstrap=settings.kafka_admin_bootstrap or settings.kafka_bootstrap,
        schema_registry_url=(
            settings.kafka_admin_schema_registry_url or settings.schema_registry_url
        ),
        security_protocol=settings.kafka_security_protocol or "PLAINTEXT",
        sasl_mechanism=settings.kafka_sasl_mechanism,
        sasl_username=settings.kafka_sasl_username,
        sasl_password=settings.kafka_sasl_password,
        label="Strimzi Kafka",
        namespace="aqp-streaming",
    )


def _build_redpanda_cluster(strimzi: StreamingCluster) -> StreamingCluster:
    """Build the Redpanda descriptor from the new ``redpanda_*`` settings.

    Falls back to the Strimzi descriptor when ``redpanda_bootstrap`` is
    empty so any code that asks for ``cluster="redpanda"`` keeps
    working in environments where Redpanda has not yet been deployed.
    """
    bootstrap = getattr(settings, "redpanda_bootstrap", "") or ""
    admin = getattr(settings, "redpanda_admin_url", "") or ""
    schema_reg = getattr(settings, "redpanda_schema_registry_url", "") or ""
    if not bootstrap:
        # Redpanda not configured yet - alias to Strimzi so everything
        # still produces. Replace ``name`` so the producer / admin
        # client logs reflect the requested cluster.
        return StreamingCluster(
            name="redpanda",
            bootstrap=strimzi.bootstrap,
            admin_bootstrap=strimzi.admin_bootstrap,
            schema_registry_url=strimzi.schema_registry_url,
            security_protocol=strimzi.security_protocol,
            sasl_mechanism=strimzi.sasl_mechanism,
            sasl_username=strimzi.sasl_username,
            sasl_password=strimzi.sasl_password,
            label="Redpanda (alias to Strimzi - not configured)",
            namespace="aqp-streaming",
        )
    return StreamingCluster(
        name="redpanda",
        bootstrap=bootstrap,
        admin_bootstrap=bootstrap,
        schema_registry_url=schema_reg,
        security_protocol=strimzi.security_protocol,
        sasl_mechanism=strimzi.sasl_mechanism,
        sasl_username=strimzi.sasl_username,
        sasl_password=strimzi.sasl_password,
        label="Redpanda",
        namespace="aqp-streaming",
    )


def _registry() -> dict[str, StreamingCluster]:
    """Return the cached cluster registry, building it on first access."""
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            strimzi = _build_strimzi_cluster()
            redpanda = _build_redpanda_cluster(strimzi)
            _CACHE = {strimzi.name: strimzi, redpanda.name: redpanda}
        return _CACHE


def reset_registry() -> None:
    """Drop the cached registry. Test helper / called when Settings reload."""
    global _CACHE
    with _LOCK:
        _CACHE = None


def list_clusters() -> list[StreamingCluster]:
    """Return every registered cluster in deterministic order."""
    return [
        _registry()[name]
        for name in sorted(_registry().keys())
    ]


def get_cluster(name: str | None = None) -> StreamingCluster:
    """Return a cluster descriptor by name (default: Strimzi).

    Raises :class:`KeyError` when the alias is unknown so the caller
    can surface a clear error rather than silently producing to the
    wrong cluster.
    """
    alias = (name or DEFAULT_CLUSTER).strip().lower()
    registry = _registry()
    if alias not in registry:
        raise KeyError(
            f"unknown streaming cluster {alias!r}; "
            f"registered: {sorted(registry.keys())}"
        )
    return registry[alias]


def cluster_for_topic(topic: str) -> StreamingCluster:
    """Resolve the cluster that owns ``topic`` based on its name prefix.

    Strips the global ``settings.kafka_topic_prefix`` before matching
    so prefixed deployments (e.g., ``aqp-prod.market.l1.aapl``) still
    route the same way as unprefixed ones.
    """
    bare = topic
    if settings.kafka_topic_prefix and bare.startswith(settings.kafka_topic_prefix):
        bare = bare[len(settings.kafka_topic_prefix):]
    for cluster_name, prefix in TOPIC_PREFIX_ROUTES:
        if bare.startswith(prefix):
            return get_cluster(cluster_name)
    return get_cluster(DEFAULT_CLUSTER)


def cluster_aliases() -> Iterable[str]:
    """Return the list of registered cluster aliases."""
    return list(_registry().keys())


__all__ = [
    "DEFAULT_CLUSTER",
    "StreamingCluster",
    "TOPIC_PREFIX_ROUTES",
    "cluster_aliases",
    "cluster_for_topic",
    "get_cluster",
    "list_clusters",
    "reset_registry",
]
