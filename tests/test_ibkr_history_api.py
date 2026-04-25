"""Route tests for IBKR historical fetch/ingest endpoints."""
from __future__ import annotations

from typing import Any

import pandas as pd
import pytest


@pytest.fixture
def fastapi_test_client():
    fastapi = pytest.importorskip("fastapi.testclient")
    from aqp.api.main import app

    return fastapi.TestClient(app)


def test_fetch_ibkr_historical_maps_validation_errors(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.data.ibkr_historical import IBKRHistoricalValidationError

    class _FakeService:
        async def fetch_bars(self, **_kwargs: Any) -> pd.DataFrame:
            raise IBKRHistoricalValidationError("bad request")

    monkeypatch.setattr("aqp.data.ibkr_historical.IBKRHistoricalService", _FakeService)

    resp = fastapi_test_client.post(
        "/data/ibkr/historical/fetch",
        json={
            "vt_symbol": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2024-01-02",
            "bar_size": "1 day",
            "what_to_show": "TRADES",
            "use_rth": True,
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    # New structured-error contract; tolerate legacy string for safety.
    detail = body.get("detail")
    if isinstance(detail, dict):
        assert "bad request" in detail.get("detail", "")
        assert detail.get("code") == "validation"
    else:
        assert "bad request" in (detail or "")


def test_fetch_ibkr_historical_returns_bars_payload(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeService:
        async def fetch_bars(self, **_kwargs: Any) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                    "vt_symbol": ["AAPL.NASDAQ", "AAPL.NASDAQ"],
                    "open": [100.0, 101.0],
                    "high": [102.0, 103.0],
                    "low": [99.0, 100.0],
                    "close": [101.0, 102.0],
                    "volume": [1_000.0, 1_100.0],
                }
            )

    monkeypatch.setattr("aqp.data.ibkr_historical.IBKRHistoricalService", _FakeService)

    resp = fastapi_test_client.post(
        "/data/ibkr/historical/fetch",
        json={
            "vt_symbol": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2024-01-02",
            "bar_size": "1 day",
            "what_to_show": "TRADES",
            "use_rth": True,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "ibkr"
    assert payload["count"] == 2
    assert len(payload["bars"]) == 2


def test_ingest_ibkr_history_enqueues_task(
    fastapi_test_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.api.routes import data as data_routes

    class _AsyncResult:
        id = "ibkr-task-123"

    class _FakeTask:
        @staticmethod
        def delay(_payload: dict[str, Any]) -> _AsyncResult:
            return _AsyncResult()

    monkeypatch.setattr(data_routes, "ingest_ibkr_historical", _FakeTask())

    resp = fastapi_test_client.post(
        "/data/ibkr/historical/ingest",
        json={
            "vt_symbol": "AAPL.NASDAQ",
            "start": "2024-01-01",
            "end": "2024-01-05",
            "bar_size": "1 day",
            "what_to_show": "TRADES",
            "use_rth": True,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["task_id"] == "ibkr-task-123"
    assert payload["stream_url"] == "/chat/stream/ibkr-task-123"
