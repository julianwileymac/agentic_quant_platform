"""Tests for the OwnershipEvent bus.

Drives the in-memory fallback so the suite doesn't need Redis.
"""
from __future__ import annotations

import pytest

from aqp.graph.events import (
    OwnershipEvent,
    OwnershipEventKind,
    emit_ownership_event,
    iter_drained_events,
    reset_fallback_queue_for_tests,
)
from aqp.graph.protocol import OwnershipEdge, OwnershipNode


@pytest.fixture(autouse=True)
def _isolate_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the fallback path so tests don't depend on Redis.
    monkeypatch.setattr("aqp.graph.events._redis_client", lambda: None)
    reset_fallback_queue_for_tests()
    yield
    reset_fallback_queue_for_tests()


def test_event_roundtrip_via_fallback() -> None:
    node = OwnershipNode(id="proj-1", kind="Project", properties={"name": "Foo"})
    emit_ownership_event(
        OwnershipEvent(kind=OwnershipEventKind.UPSERT_NODE, node=node)
    )
    out = list(iter_drained_events(max_events=10))
    assert len(out) == 1
    assert out[0].kind == OwnershipEventKind.UPSERT_NODE
    assert out[0].node == node


def test_drain_respects_max_events() -> None:
    for i in range(5):
        emit_ownership_event(
            OwnershipEvent(
                kind=OwnershipEventKind.UPSERT_NODE,
                node=OwnershipNode(id=f"n{i}", kind="Resource"),
            )
        )
    first = list(iter_drained_events(max_events=3))
    second = list(iter_drained_events(max_events=10))
    assert len(first) == 3
    assert len(second) == 2  # leftover


def test_edge_payload_roundtrip() -> None:
    edge = OwnershipEdge(
        from_id="user-1",
        from_kind="User",
        to_id="ws-1",
        to_kind="Workspace",
        relation="MEMBER_OF",
        properties={"role": "owner"},
    )
    emit_ownership_event(
        OwnershipEvent(kind=OwnershipEventKind.UPSERT_EDGE, edge=edge)
    )
    out = list(iter_drained_events(max_events=10))
    assert out[0].edge == edge
    assert out[0].edge.properties == {"role": "owner"}


def test_payload_serialisation_is_json_safe() -> None:
    ev = OwnershipEvent(
        kind=OwnershipEventKind.UPSERT_NODE,
        node=OwnershipNode(id="x", kind="Resource", properties={"tags": ["a", "b"]}),
    )
    payload = ev.to_payload()
    restored = OwnershipEvent.from_payload(payload)
    assert restored.kind == ev.kind
    assert restored.node == ev.node
