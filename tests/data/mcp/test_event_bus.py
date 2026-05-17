from __future__ import annotations

from aqp.data.mcp.event_bus import FeedEvent, FeedEventBus


def test_publish_dispatches_to_handlers() -> None:
    bus = FeedEventBus()
    seen: list[FeedEvent] = []

    bus.subscribe(lambda event: seen.append(event))
    bus.publish(FeedEvent(kind="upsert", data_source_id="feed-1", payload={"x": 1}))

    assert len(seen) == 1
    assert seen[0].kind == "upsert"
    assert seen[0].data_source_id == "feed-1"
    assert seen[0].payload["x"] == 1


def test_unsubscribe_stops_dispatch() -> None:
    bus = FeedEventBus()
    seen: list[FeedEvent] = []

    unsubscribe = bus.subscribe(lambda event: seen.append(event))
    unsubscribe()
    bus.publish(FeedEvent(kind="delete", data_source_id="feed-2"))

    assert seen == []


def test_handler_exception_does_not_break_bus() -> None:
    bus = FeedEventBus()
    seen: list[str] = []

    def _bad_handler(_event: FeedEvent) -> None:
        raise RuntimeError("boom")

    def _good_handler(event: FeedEvent) -> None:
        seen.append(event.kind)

    bus.subscribe(_bad_handler)
    bus.subscribe(_good_handler)
    bus.publish(FeedEvent(kind="sync_triggered", data_source_id="feed-3"))

    assert seen == ["sync_triggered"]
