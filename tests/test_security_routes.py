"""Tests for the per-security reference-data API (`/data/security/*`).

We stub the Redis cache layer in-memory and monkey-patch
``YahooFinanceSource`` to avoid any real network calls.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from aqp.data import cache as cache_mod


# --------------------------------------------------------------------------
# In-memory stand-ins (shared with the cache module tests).
# --------------------------------------------------------------------------


class _MemoryRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> bool:  # noqa: ARG002
        self._store[key] = value
        return True

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if self._store.pop(key, None) is not None:
                deleted += 1
        return deleted

    def scan(self, cursor: int = 0, match: str | None = None, count: int = 100):  # noqa: ARG002
        import fnmatch

        keys = [k for k in self._store if match is None or fnmatch.fnmatch(k, match)]
        return 0, keys


class _AsyncMemoryRedis(_MemoryRedis):
    async def get(self, key: str) -> str | None:  # type: ignore[override]
        return super().get(key)

    async def setex(self, key: str, ttl: int, value: str) -> bool:  # type: ignore[override]
        return super().setex(key, ttl, value)

    async def delete(self, *keys: str) -> int:  # type: ignore[override]
        return super().delete(*keys)

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _MemoryRedis:
    sync = _MemoryRedis()
    async_store = _AsyncMemoryRedis()
    async_store._store = sync._store

    monkeypatch.setattr(cache_mod, "_sync_client", lambda: sync)
    monkeypatch.setattr(cache_mod, "_async_client", lambda: async_store)
    return sync


@pytest.fixture
def client(fake_redis: _MemoryRedis) -> TestClient:
    from aqp.api.main import app

    return TestClient(app)


# --------------------------------------------------------------------------
# Stub provider helpers
# --------------------------------------------------------------------------


class _StubSource:
    """Records call counts and returns canned payloads."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def _bump(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def fetch_fundamentals_one(self, ticker: str) -> dict[str, Any]:
        self._bump("fundamentals")
        return {"ticker": ticker, "name": "Apple Inc.", "sector": "Technology", "market_cap": 3.0e12}

    def fetch_news(self, ticker: str, limit: int = 20) -> list[dict[str, Any]]:
        self._bump("news")
        return [
            {
                "title": "Apple hits new high",
                "publisher": "Reuters",
                "link": "https://example.com",
                "published": "2026-01-01T00:00:00+00:00",
                "summary": "summary",
                "thumbnail": None,
                "related": ["MSFT"],
            }
        ][:limit]

    def fetch_calendar(self, ticker: str) -> dict[str, Any]:
        self._bump("calendar")
        return {
            "ticker": ticker,
            "earnings_date": "2026-01-30",
            "ex_dividend_date": "2026-02-10",
            "dividend_date": "2026-02-15",
            "earnings_average": 2.1,
            "earnings_high": 2.3,
            "earnings_low": 2.0,
            "revenue_average": 120_000_000.0,
            "revenue_high": 125_000_000.0,
            "revenue_low": 115_000_000.0,
            "earnings_history": [],
        }

    def fetch_corporate_actions(self, ticker: str) -> dict[str, Any]:
        self._bump("corporate")
        return {
            "ticker": ticker,
            "dividends": [{"date": "2026-01-01T00:00:00+00:00", "value": 0.24}],
            "splits": [],
            "institutional_holders": [],
        }

    def fetch_quote(self, ticker: str) -> dict[str, Any]:
        self._bump("quote")
        return {
            "ticker": ticker,
            "last": 190.0,
            "previous_close": 189.0,
            "change": 1.0,
            "change_pct": 0.5291,
            "open": 189.5,
            "day_high": 191.0,
            "day_low": 188.9,
            "volume": 52_000_000,
            "currency": "USD",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }


@pytest.fixture
def stub_source(monkeypatch: pytest.MonkeyPatch) -> _StubSource:
    stub = _StubSource()

    from aqp.data import ingestion as ingestion_mod
    from aqp.data import fundamentals as fundamentals_mod

    class _Factory:
        def __new__(cls, *args, **kwargs):  # noqa: ARG002
            return stub

    monkeypatch.setattr(ingestion_mod, "YahooFinanceSource", _Factory)
    monkeypatch.setattr(fundamentals_mod.settings, "alpha_vantage_api_key", "", raising=False)
    monkeypatch.setattr(fundamentals_mod.settings, "fundamentals_provider", "yfinance", raising=False)

    # Ensure ``yfinance`` import check passes.  We fake the module so
    # ``_require_yfinance`` doesn't 503.
    import sys
    import types

    if "yfinance" not in sys.modules:
        sys.modules["yfinance"] = types.ModuleType("yfinance")
    return stub


# --------------------------------------------------------------------------
# Endpoint coverage
# --------------------------------------------------------------------------


def test_fundamentals_200(client: TestClient, stub_source: _StubSource) -> None:
    resp = client.get("/data/security/AAPL.NASDAQ/fundamentals")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["name"] == "Apple Inc."
    assert body["cached"] is False
    assert stub_source.calls["fundamentals"] == 1


def test_fundamentals_cache_hit(client: TestClient, stub_source: _StubSource) -> None:
    client.get("/data/security/AAPL/fundamentals")
    resp = client.get("/data/security/AAPL/fundamentals")
    assert resp.status_code == 200
    assert resp.json()["cached"] is True
    # Only one call into the provider even after two HTTP calls.
    assert stub_source.calls["fundamentals"] == 1


def test_fundamentals_prefers_alpha_vantage_when_configured(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.data import fundamentals as fundamentals_mod

    monkeypatch.setattr(fundamentals_mod.settings, "fundamentals_provider", "auto", raising=False)
    monkeypatch.setattr(fundamentals_mod.settings, "alpha_vantage_api_key", "demo-key", raising=False)
    monkeypatch.setattr(
        fundamentals_mod,
        "_fetch_alpha_vantage_fundamentals",
        lambda ticker: {
            "ticker": ticker,
            "name": "Apple Inc.",
            "sector": "Technology",
            "market_cap": 3.0e12,
            "trailing_pe": 31.2,
        },
    )
    monkeypatch.setattr(
        fundamentals_mod,
        "_fetch_yfinance_fundamentals",
        lambda ticker: (_ for _ in ()).throw(AssertionError(f"yfinance fallback should not run for {ticker}")),
    )

    resp = client.get("/data/security/AAPL/fundamentals")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["trailing_pe"] == 31.2


def test_news_endpoint_limits_and_roundtrips(
    client: TestClient,
    stub_source: _StubSource,
) -> None:
    resp = client.get("/data/security/AAPL/news?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["publisher"] == "Reuters"


def test_calendar_endpoint(client: TestClient, stub_source: _StubSource) -> None:
    resp = client.get("/data/security/AAPL/calendar")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["earnings_average"] == 2.1


def test_corporate_endpoint(client: TestClient, stub_source: _StubSource) -> None:
    resp = client.get("/data/security/AAPL/corporate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dividends"][0]["value"] == 0.24


def test_quote_endpoint(client: TestClient, stub_source: _StubSource) -> None:
    resp = client.get("/data/security/AAPL/quote")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last"] == 190.0
    assert body["change_pct"] is not None


def test_404_when_provider_returns_empty(
    client: TestClient,
    stub_source: _StubSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(_ticker: str) -> dict[str, Any]:
        raise ValueError("no fundamentals payload for 'ZZZZZZ'")

    stub_source.fetch_fundamentals_one = _raise  # type: ignore[assignment]
    resp = client.get("/data/security/ZZZZZZ/fundamentals")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    # FastAPI wraps our dict in ``detail``
    inner = body["detail"]
    assert inner["code"] == "empty_payload"


def test_503_when_yfinance_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.data import fundamentals as fundamentals_mod

    monkeypatch.setattr(fundamentals_mod.settings, "alpha_vantage_api_key", "", raising=False)
    monkeypatch.setattr(fundamentals_mod.settings, "fundamentals_provider", "yfinance", raising=False)

    import builtins

    real_import = builtins.__import__

    def _block_yfinance(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "yfinance":
            raise ImportError("yfinance not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_yfinance)
    import sys

    sys.modules.pop("yfinance", None)

    resp = client.get("/data/security/AAPL/fundamentals")
    assert resp.status_code == 503
    inner = resp.json()["detail"]
    assert inner["code"] == "yfinance_missing"


def test_cache_invalidation_endpoint(
    client: TestClient,
    stub_source: _StubSource,
    fake_redis: _MemoryRedis,
) -> None:
    client.get("/data/security/AAPL/fundamentals")
    client.get("/data/security/AAPL/quote")
    # Populated redis
    assert len(fake_redis._store) > 0

    resp = client.delete("/data/security/AAPL/cache")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["removed"] >= 1
