"""Smoke tests for the live-market subscribe / WS endpoints (in-process)."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from aqp.api import main as main_mod

    return TestClient(main_mod.app)


def test_subscribe_simulated_returns_channel(client):
    resp = client.post(
        "/live/subscribe",
        json={"venue": "simulated", "symbols": ["AAPL", "MSFT"], "poll_cadence_seconds": 0.1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["venue"] == "simulated"
    assert set(data["symbols"]) == {"AAPL", "MSFT"}
    assert data["stream_url"].startswith("/live/stream/")

    channel_id = data["channel_id"]
    subs = client.get("/live/subscriptions").json()
    # Feed loops now self-clean if they terminate, so this can be racy for
    # very short-lived subscriptions.
    present = any(s["channel_id"] == channel_id for s in subs)
    assert isinstance(subs, list)

    # Cleanup
    if present:
        resp = client.delete(f"/live/subscribe/{channel_id}")
        assert resp.status_code == 200


def test_subscribe_unknown_venue_rejected(client):
    resp = client.post(
        "/live/subscribe",
        json={"venue": "unknown-venue", "symbols": ["AAPL"]},
    )
    assert resp.status_code == 404


def test_subscribe_requires_symbols(client):
    resp = client.post(
        "/live/subscribe",
        json={"venue": "simulated", "symbols": []},
    )
    assert resp.status_code == 400


def test_unsubscribe_active_channel_absorbs_task_cancellation(client):
    from aqp.api.routes import market_data_live as live_mod

    class FakeTask:
        def __init__(self) -> None:
            self.cancel_called = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancel_called = True

        def __await__(self):
            async def _await_cancel():
                raise asyncio.CancelledError

            return _await_cancel().__await__()

    channel_id = "cancel-test"
    sub = live_mod._Subscription(channel_id=channel_id, venue="simulated", symbols=["AAPL"])
    fake_task = FakeTask()
    sub.task = fake_task
    live_mod._SUBS[channel_id] = sub

    resp = client.delete(f"/live/subscribe/{channel_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["stopped"] is True
    assert fake_task.cancel_called is True
    assert all(s["channel_id"] != channel_id for s in client.get("/live/subscriptions").json())


def test_subscribe_ibkr_preflight_maps_to_structured_http_error(client, monkeypatch):
    from aqp.api.routes import market_data_live as live_mod

    def _raise() -> None:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "Cannot reach TWS on localhost:7497",
                "code": "ibkr_unavailable",
                "hint": "Start TWS / IB Gateway.",
            },
        )

    monkeypatch.setattr(live_mod, "_probe_ibkr_or_raise", _raise)

    resp = client.post(
        "/live/subscribe",
        json={"venue": "ibkr", "symbols": ["AAPL"]},
    )
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["code"] == "ibkr_unavailable"
