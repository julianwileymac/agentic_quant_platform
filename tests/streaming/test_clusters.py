"""Smoke tests for the side-by-side streaming cluster registry."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_streaming_registry() -> None:
    from aqp.streaming.clusters import reset_registry

    reset_registry()
    yield
    reset_registry()


def test_strimzi_cluster_resolves_to_legacy_kafka_settings() -> None:
    from aqp.streaming.clusters import get_cluster

    cluster = get_cluster("strimzi")
    assert cluster.name == "strimzi"
    # Defaults from settings.kafka_bootstrap (localhost:9092 in unit tests).
    assert cluster.bootstrap


def test_redpanda_cluster_resolves_through_topology() -> None:
    from aqp.streaming.clusters import get_cluster

    redpanda = get_cluster("redpanda")
    strimzi = get_cluster("strimzi")
    # The shipped topology.yaml declares a redpanda endpoint in the
    # `aqp-streaming` namespace. The topology fallback populates
    # ``settings.redpanda_bootstrap`` from that endpoint so call sites
    # that ask for redpanda hit Redpanda directly (not Strimzi).
    assert redpanda.name == "redpanda"
    assert "redpanda" in redpanda.bootstrap
    # Strimzi keeps its distinct bootstrap so the side-by-side topology
    # is preserved.
    assert redpanda.bootstrap != strimzi.bootstrap


def test_redpanda_cluster_aliases_to_strimzi_when_topology_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.streaming.clusters import get_cluster, reset_registry

    # Force the absent-Redpanda safety net by clearing the topology-
    # populated bootstrap. Mirrors a deployment that has not yet rolled
    # out Redpanda alongside Strimzi.
    from aqp.config import settings

    monkeypatch.setattr(settings, "redpanda_bootstrap", "", raising=False)
    reset_registry()
    redpanda = get_cluster("redpanda")
    strimzi = get_cluster("strimzi")
    assert redpanda.name == "redpanda"
    assert redpanda.bootstrap == strimzi.bootstrap


def test_topic_prefix_routing() -> None:
    from aqp.streaming.clusters import cluster_for_topic

    assert cluster_for_topic("market.l1.aapl").name == "redpanda"
    assert cluster_for_topic("market.l2.aapl").name == "redpanda"
    assert cluster_for_topic("execution.orders.alpaca").name == "redpanda"
    assert cluster_for_topic("agentic.state.research").name == "redpanda"
    # Existing factor / RAG / regulatory topics stay on strimzi.
    assert cluster_for_topic("aqp.factor.exports.v1").name == "strimzi"
    assert cluster_for_topic("market.deadletter.v1").name == "strimzi"


def test_unknown_cluster_alias_raises_keyerror() -> None:
    from aqp.streaming.clusters import get_cluster

    with pytest.raises(KeyError):
        get_cluster("kafka-3000")


def test_list_clusters_returns_both() -> None:
    from aqp.streaming.clusters import list_clusters

    aliases = {c.name for c in list_clusters()}
    assert aliases == {"strimzi", "redpanda"}
