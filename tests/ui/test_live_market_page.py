"""Smoke-render tests for the unified Live Market page.

These tests mount the page via ``reacton.render`` with the API client
fully stubbed.  They exercise:

* the default render path (no selected tab / empty bars)
* that all new tabs wire up without raising
* that the yfinance service helpers are not hit when they'd otherwise
  try to round-trip to the FastAPI layer
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
import reacton
import solara


@pytest.fixture(autouse=True)
def _patch_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out every network-touching call the page makes."""
    import aqp.ui.api_client as api_client
    import aqp.ui.services.security as sec

    def _fake_get(path: str, **_kwargs: Any) -> Any:
        if path.endswith("/live/subscriptions"):
            return []
        if "/ibkr/historical/availability" in path:
            return {"ok": True, "message": "probe ok", "host": "127.0.0.1", "port": 7497}
        return {}

    monkeypatch.setattr(api_client, "get", _fake_get)
    monkeypatch.setattr(api_client, "post", lambda *_a, **_k: {"task_id": "t"})
    monkeypatch.setattr(api_client, "delete", lambda *_a, **_k: {"ok": True})

    # Security services: return stable canned payloads.  Tests don't
    # need yfinance or Redis.
    fixtures: dict[str, dict[str, Any]] = {
        "fundamentals": {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "market_cap": 3.0e12,
            "trailing_pe": 28.5,
            "dividend_yield": 0.0055,
            "summary": "Apple designs and builds consumer electronics.",
            "cached": False,
        },
        "news": {"ticker": "AAPL", "count": 1, "items": [
            {
                "title": "Apple hits new high",
                "publisher": "Reuters",
                "link": "https://example.com",
                "published": "2026-01-01T00:00:00+00:00",
                "summary": "summary",
                "thumbnail": None,
                "related": [],
            }
        ], "cached": False},
        "calendar": {"ticker": "AAPL", "earnings_date": "2026-04-30"},
        "corporate": {
            "ticker": "AAPL",
            "dividends": [{"date": "2026-01-01T00:00:00+00:00", "value": 0.24}],
            "splits": [],
            "institutional_holders": [],
        },
        "quote": {
            "ticker": "AAPL",
            "last": 192.30,
            "previous_close": 190.00,
            "change": 2.30,
            "change_pct": 1.21,
            "volume": 1.5e7,
            "currency": "USD",
        },
    }

    monkeypatch.setattr(sec, "get_fundamentals", lambda s: fixtures["fundamentals"])
    monkeypatch.setattr(sec, "get_news", lambda s, limit=20: fixtures["news"])
    monkeypatch.setattr(sec, "get_calendar", lambda s: fixtures["calendar"])
    monkeypatch.setattr(sec, "get_corporate", lambda s: fixtures["corporate"])
    monkeypatch.setattr(sec, "get_quote", lambda s: fixtures["quote"])
    monkeypatch.setattr(
        sec,
        "get_historical_bars",
        lambda **_k: pd.DataFrame(
            {
                "timestamp": pd.bdate_range("2024-01-01", periods=30),
                "vt_symbol": ["AAPL.NASDAQ"] * 30,
                "open": list(range(30)),
                "high": [x + 1 for x in range(30)],
                "low": [x - 1 for x in range(30)],
                "close": [x + 0.5 for x in range(30)],
                "volume": [1_000_000] * 30,
            }
        ),
    )
    monkeypatch.setattr(
        sec,
        "get_ibkr_availability",
        lambda refresh=False: sec.IBKRAvailability(ok=True, message="ok", host="127.0.0.1", port=7497),
    )

    # Patch the same helpers on the page module (they are imported by name).
    from aqp.ui.pages import live_market as page_mod

    monkeypatch.setattr(page_mod, "get_fundamentals", lambda s: fixtures["fundamentals"])
    monkeypatch.setattr(page_mod, "get_news", lambda s, limit=20: fixtures["news"])
    monkeypatch.setattr(page_mod, "get_calendar", lambda s: fixtures["calendar"])
    monkeypatch.setattr(page_mod, "get_corporate", lambda s: fixtures["corporate"])
    monkeypatch.setattr(page_mod, "get_quote", lambda s: fixtures["quote"])
    monkeypatch.setattr(page_mod, "get_historical_bars", lambda **k: sec.get_historical_bars(**k))
    monkeypatch.setattr(
        page_mod,
        "get_ibkr_availability",
        lambda refresh=False: sec.IBKRAvailability(ok=True, message="ok"),
    )


def test_live_market_default_render() -> None:
    from aqp.ui.pages.live_market import Page

    widget, rc = reacton.render(Page(), handle_error=False)
    try:
        assert widget is not None
    finally:
        rc.close()


def test_live_market_handles_security_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.ui.pages import live_market as page_mod
    from aqp.ui.services.security import SecurityError

    def _raise(*_a: Any, **_k: Any) -> Any:
        raise SecurityError(status=404, code="empty_payload", detail="no data", hint="try later")

    monkeypatch.setattr(page_mod, "get_fundamentals", _raise)
    monkeypatch.setattr(page_mod, "get_news", _raise)
    monkeypatch.setattr(page_mod, "get_quote", _raise)

    widget, rc = reacton.render(page_mod.Page(), handle_error=False)
    try:
        assert widget is not None
    finally:
        rc.close()


def test_chart_builds_with_all_panels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the chart builder via the page to ensure all panels render."""
    from aqp.ui.components import build_security_figure

    bars = pd.DataFrame(
        {
            "timestamp": pd.bdate_range("2024-01-01", periods=120),
            "open": list(range(120)),
            "high": [x + 1 for x in range(120)],
            "low": [x - 1 for x in range(120)],
            "close": [x + 0.5 for x in range(120)],
            "volume": [1_000_000] * 120,
        }
    )
    fig = build_security_figure(
        bars,
        features={"sma_20", "ema_20", "vwap", "volume", "rsi", "macd", "drawdown", "bbands"},
    )
    # Rough check: price pane + 4 panels + various overlay traces
    assert len(fig.data) >= 6


def test_watchlist_tab_renders_subscription_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.ui.pages import live_market as page_mod

    @solara.component
    def _fake_streamer(*_args: Any, **_kwargs: Any) -> None:
        solara.Markdown("streamer")

    @solara.component
    def _host() -> None:
        page_mod._render_watchlist_tab(
            focused_channel="abc123",
            focused_symbols=["AAPL"],
            subs=[
                {"channel_id": "abc123", "venue": "ibkr", "symbols": ["AAPL"]},
                {"channel_id": "def456", "venue": "simulated", "symbols": ["MSFT", "SPY"]},
            ],
            on_status=lambda _status: None,
            on_focus=lambda _cid, _symbols: None,
            on_unsubscribe=lambda _cid: None,
            on_unsubscribe_all=lambda: None,
        )

    monkeypatch.setattr(page_mod, "LiveStreamer", _fake_streamer)
    widget, rc = reacton.render(_host(), handle_error=False)
    try:
        assert widget is not None
    finally:
        rc.close()


def test_watchlist_tab_handles_subs_without_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.ui.pages import live_market as page_mod

    @solara.component
    def _fake_streamer(*_args: Any, **_kwargs: Any) -> None:
        solara.Markdown("streamer")

    @solara.component
    def _host() -> None:
        page_mod._render_watchlist_tab(
            focused_channel="",
            focused_symbols=[],
            subs=[
                {"channel_id": "abc123", "venue": "ibkr", "symbols": ["AAPL"]},
            ],
            on_status=lambda _status: None,
            on_focus=lambda _cid, _symbols: None,
            on_unsubscribe=lambda _cid: None,
            on_unsubscribe_all=lambda: None,
        )

    monkeypatch.setattr(page_mod, "LiveStreamer", _fake_streamer)
    widget, rc = reacton.render(_host(), handle_error=False)
    try:
        assert widget is not None
    finally:
        rc.close()
