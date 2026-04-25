"""Regression tests for provider-policy resolver and wiring."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _sample_bars(vt_symbol: str) -> pd.DataFrame:
    ts = datetime(2024, 1, 2, tzinfo=timezone.utc)
    return pd.DataFrame(
        [
            {
                "timestamp": ts,
                "vt_symbol": vt_symbol,
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 1_000_000.0,
            }
        ]
    )


def test_ingest_falls_back_to_yfinance_when_av_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aqp.data import ingestion as ingestion_mod

    calls = {"av": 0, "yahoo": 0}

    class _FailingAV:
        name = "alpha_vantage"

        def fetch(self, symbols, start, end, interval="1d"):  # noqa: ANN001, ARG002
            calls["av"] += 1
            raise RuntimeError("rate limited")

    class _Yahoo:
        name = "yahoo"

        def fetch(self, symbols, start, end, interval="1d"):  # noqa: ANN001, ARG002
            calls["yahoo"] += 1
            ticker = str(list(symbols)[0]).upper()
            return _sample_bars(f"{ticker}.NASDAQ")

    monkeypatch.setattr(ingestion_mod.settings, "alpha_vantage_api_key", "demo-key", raising=False)
    monkeypatch.setattr(ingestion_mod.settings, "market_bars_provider", "auto", raising=False)
    monkeypatch.setattr(ingestion_mod.settings, "universe_provider", "config", raising=False)
    monkeypatch.setattr(ingestion_mod, "AlphaVantageSource", _FailingAV)
    monkeypatch.setattr(ingestion_mod, "YahooFinanceSource", _Yahoo)
    monkeypatch.setattr(ingestion_mod, "write_parquet", lambda df, parquet_dir=None, overwrite=False: tmp_path)  # noqa: ARG005
    monkeypatch.setattr("aqp.data.catalog.register_dataset_version", lambda **kwargs: {})  # noqa: ARG005

    out = ingestion_mod.ingest(
        symbols=["AAPL"],
        start="2024-01-01",
        end="2024-01-05",
        interval="1d",
        source="auto",
    )
    assert not out.empty
    assert calls["av"] == 1
    assert calls["yahoo"] == 1
    assert out["vt_symbol"].iloc[0] == "AAPL.NASDAQ"


def test_resolve_fundamentals_falls_back_to_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.data import fundamentals as fundamentals_mod

    monkeypatch.setattr(fundamentals_mod.settings, "fundamentals_provider", "auto", raising=False)
    monkeypatch.setattr(fundamentals_mod.settings, "alpha_vantage_api_key", "demo-key", raising=False)
    monkeypatch.setattr(
        fundamentals_mod,
        "_fetch_alpha_vantage_fundamentals",
        lambda ticker: (_ for _ in ()).throw(RuntimeError("av timeout")),
    )
    monkeypatch.setattr(
        fundamentals_mod,
        "_fetch_yfinance_fundamentals",
        lambda ticker: {"ticker": ticker, "trailing_pe": 21.0, "sector": "Technology"},
    )

    payload = fundamentals_mod.resolve_fundamentals_one("AAPL")
    assert payload["ticker"] == "AAPL"
    assert payload["trailing_pe"] == 21.0


def test_data_ingest_route_passes_source_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.api.main import app
    from aqp.api.routes import data as data_route

    captured: dict[str, tuple] = {}

    class _Result:
        id = "task-123"

    def _delay(*args):
        captured["args"] = args
        return _Result()

    monkeypatch.setattr(data_route.ingest_yahoo, "delay", _delay)
    client = TestClient(app)
    response = client.post(
        "/data/ingest",
        json={
            "symbols": ["AAPL", "MSFT"],
            "start": "2024-01-01",
            "end": "2024-01-31",
            "interval": "1d",
            "source": "alpha_vantage",
        },
    )
    assert response.status_code == 200, response.text
    assert captured["args"] == (
        ["AAPL", "MSFT"],
        "2024-01-01",
        "2024-01-31",
        "1d",
        "alpha_vantage",
    )
