"""Streaming helpers — WS connectivity and polling fallback."""
from __future__ import annotations

import sys
import time
from types import ModuleType

import pytest


def test_iter_ws_returns_error_when_websockets_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """With ``websockets`` absent, ``iter_ws`` should return cleanly.

    The generator yields nothing in the "module not found" branch so the
    caller's poll fallback can take over.
    """
    # Temporarily pretend ``websockets.sync.client`` cannot be imported.
    original_sync = sys.modules.get("websockets.sync.client")
    sys.modules["websockets.sync.client"] = None  # type: ignore[assignment]
    try:
        from aqp.ui import api_client

        # Re-execute the iterator; because the ``from ... import connect``
        # happens inside the generator function it is evaluated lazily.
        results = list(api_client.iter_ws("/chat/stream/deadbeef"))
        assert results == [] or any(
            "ws connection closed" in (r.get("message") or "").lower() for r in results
        )
    finally:
        if original_sync is None:
            sys.modules.pop("websockets.sync.client", None)
        else:
            sys.modules["websockets.sync.client"] = original_sync


def test_spawn_stream_falls_back_to_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the WS side never yields anything, the polling loop must take over.

    We exercise ``_spawn_stream`` with a custom ``iter_ws`` that yields
    nothing and a polling callback that feeds the message handler.
    """
    import solara

    from aqp.ui.components.data import task_streamer as ts_module

    messages: list[dict] = []

    def fake_iter_ws(_path: str):
        return iter([])  # no WS messages

    def poll_source() -> list[dict]:
        return [{"stage": "info", "message": "tick"}]

    monkeypatch.setattr(ts_module, "iter_ws", fake_iter_ws)
    stop_flag = solara.Reactive(False)
    teardown = ts_module._spawn_stream(
        "/chat/stream/abc",
        on_message=messages.append,
        stop_flag=stop_flag,
        poll_fallback=poll_source,
        poll_interval=0.01,
    )
    # Let the polling loop tick a few times.
    deadline = time.time() + 1.0
    while time.time() < deadline and len(messages) < 3:
        time.sleep(0.05)
    teardown()
    assert len(messages) >= 1
    assert all(m.get("message") == "tick" for m in messages)
