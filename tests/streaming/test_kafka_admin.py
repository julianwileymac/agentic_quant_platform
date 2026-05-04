"""Hermetic tests for the Kafka admin facade.

We mock out ``confluent_kafka.admin.AdminClient`` so the suite never
touches a real broker. The goal is to verify metadata translation,
error wrapping, and the lazy-singleton plumbing.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


class _FakeFuture:
    def __init__(self, result: Any | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def result(self) -> Any:
        if self._error is not None:
            raise self._error
        return self._result


class _FakeAdmin:
    def __init__(self) -> None:
        self.created: list[Any] = []
        self.deleted: list[str] = []

    def list_topics(self, timeout: float = 0) -> Any:
        partitions = {0: SimpleNamespace(replicas=[1, 2])}
        topics = {
            "market.bar.v1": SimpleNamespace(partitions=partitions),
            "__consumer_offsets": SimpleNamespace(partitions={0: SimpleNamespace(replicas=[1])}),
        }
        return SimpleNamespace(topics=topics)

    def create_topics(self, new_topics, request_timeout: float = 0) -> dict[str, _FakeFuture]:
        for nt in new_topics:
            self.created.append(nt)
        return {nt.topic: _FakeFuture(result=None) for nt in new_topics}

    def delete_topics(self, names, request_timeout: float = 0) -> dict[str, _FakeFuture]:
        for n in names:
            self.deleted.append(n)
        return {n: _FakeFuture(result=None) for n in names}

    def list_consumer_groups(self, request_timeout: float = 0) -> _FakeFuture:
        return _FakeFuture(
            result=SimpleNamespace(
                valid=[
                    SimpleNamespace(group_id="aqp-live", state="STABLE", member_count=2)
                ]
            )
        )


def test_list_topics_filters_internal(monkeypatch) -> None:
    from aqp.streaming.admin.kafka_admin import NativeKafkaAdmin

    admin = NativeKafkaAdmin(config={"bootstrap.servers": "localhost:9092"})
    fake = _FakeAdmin()
    monkeypatch.setattr(admin, "_get_client", lambda: fake)

    rows = admin.list_topics(include_internal=False)
    assert [r.name for r in rows] == ["market.bar.v1"]
    assert rows[0].partitions == 1
    assert rows[0].replication_factor == 2

    rows_all = admin.list_topics(include_internal=True)
    assert {r.name for r in rows_all} == {"market.bar.v1", "__consumer_offsets"}


def test_create_topic_uses_admin_future(monkeypatch) -> None:
    from aqp.streaming.admin import kafka_admin as ka

    admin = ka.NativeKafkaAdmin(config={"bootstrap.servers": "localhost:9092"})
    fake = _FakeAdmin()
    monkeypatch.setattr(admin, "_get_client", lambda: fake)

    class _NewTopic:
        def __init__(self, topic, num_partitions, replication_factor, config):
            self.topic = topic
            self.num_partitions = num_partitions
            self.replication_factor = replication_factor
            self.config = config

    monkeypatch.setattr(ka, "__import__", __import__)  # noqa: F401
    monkeypatch.setitem(
        __import__("sys").modules,
        "confluent_kafka.admin",
        SimpleNamespace(AdminClient=lambda *_args, **_kw: fake, NewTopic=_NewTopic),
    )

    summary = admin.create_topic("market.bar.v1", partitions=3, replication_factor=2)
    assert summary.name == "market.bar.v1"
    assert fake.created and fake.created[0].topic == "market.bar.v1"


def test_consumer_groups_translates_payload(monkeypatch) -> None:
    from aqp.streaming.admin.kafka_admin import NativeKafkaAdmin

    admin = NativeKafkaAdmin(config={"bootstrap.servers": "localhost:9092"})
    monkeypatch.setattr(admin, "_get_client", lambda: _FakeAdmin())
    rows = admin.list_consumer_groups()
    assert rows[0].group_id == "aqp-live"
    assert rows[0].state == "STABLE"
    assert rows[0].members == 2
