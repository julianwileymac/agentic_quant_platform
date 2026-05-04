from __future__ import annotations

import pytest


def test_rate_limiter_snapshot_shape() -> None:
    from aqp.data.sources.alpha_vantage import RateLimiter

    limiter = RateLimiter(rpm=10, daily=25)
    limiter.acquire()
    snap = limiter.snapshot()
    assert snap.rpm_limit == 10
    assert snap.daily_limit == 25
    assert snap.requests_today == 1
    assert snap.tokens_available <= 9


def test_load_api_key_non_strict_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.data.sources.alpha_vantage import _credentials, load_api_key

    monkeypatch.setattr(_credentials.settings, "alpha_vantage_api_key", "")
    monkeypatch.setattr(_credentials.settings, "alpha_vantage_api_key_file", "")
    monkeypatch.delenv("AQP_ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)

    assert load_api_key(strict=False, extra_paths=[]) == ""


def test_payload_error_classification() -> None:
    from aqp.data.sources.alpha_vantage._errors import (
        InvalidSymbolError,
        RateLimitError,
        classify_payload,
    )

    err = classify_payload({"Note": "Thank you for using Alpha Vantage! Our standard API rate limit is reached."})
    assert isinstance(err, RateLimitError)
    premium_worded = classify_payload(
        {
            "Information": (
                "Minute-level rate limit exceed. Please stay under the number of API "
                "requests per minute for your premium subscription plan."
            )
        }
    )
    assert isinstance(premium_worded, RateLimitError)
    burst = classify_payload({"Information": "Burst pattern detected. Please spread requests evenly."})
    assert isinstance(burst, RateLimitError)
    invalid_call = classify_payload({"Information": "Invalid API call. Please retry or visit the documentation."})
    assert isinstance(invalid_call, InvalidSymbolError)


def test_coerce_stock_intraday_interval() -> None:
    from aqp.data.sources.alpha_vantage.endpoints._base import coerce_stock_intraday_interval

    assert coerce_stock_intraday_interval(None) == "5min"
    assert coerce_stock_intraday_interval("") == "5min"
    assert coerce_stock_intraday_interval("5min") == "5min"
    assert coerce_stock_intraday_interval("5m") == "5min"
    assert coerce_stock_intraday_interval("1h") == "60min"
    assert coerce_stock_intraday_interval("1d") == "5min"


def test_timeseries_payload_normalization() -> None:
    from aqp.data.sources.alpha_vantage.endpoints._base import BaseEndpoint

    payload = BaseEndpoint._time_series(
        {
            "Meta Data": {"1. Symbol": "IBM"},
            "Time Series (Daily)": {
                "2024-01-02": {
                    "1. open": "1.0",
                    "2. high": "2.0",
                    "3. low": "0.5",
                    "4. close": "1.5",
                    "6. volume": "100",
                }
            },
        }
    )
    assert payload.metadata["symbol"] == "IBM"
    assert payload.bars[0]["timestamp"] == "2024-01-02"
    assert payload.bars[0]["open"] == "1.0"


def test_alpha_vantage_source_reuses_injected_client() -> None:
    from types import SimpleNamespace

    from aqp.data.ingestion import AlphaVantageSource

    calls: list[str] = []

    class _Timeseries:
        def daily_adjusted(self, symbol: str, outputsize: str):
            calls.append(f"{symbol}:{outputsize}")
            return SimpleNamespace(
                bars=[
                    {
                        "timestamp": "2024-01-02",
                        "open": "1",
                        "high": "2",
                        "low": "1",
                        "close": "2",
                        "volume": "100",
                    }
                ]
            )

    class _Client:
        timeseries = _Timeseries()
        closed = False

        def close(self):
            self.closed = True

    client = _Client()
    source = AlphaVantageSource(client=client)

    frame = source.fetch(["AAPL.NASDAQ", "MSFT.NASDAQ"], "2024-01-01", "2024-01-03", "1d")

    assert calls == ["AAPL:full", "MSFT:full"]
    assert sorted(frame["vt_symbol"].unique().tolist()) == ["AAPL.NASDAQ", "MSFT.NASDAQ"]
    assert client.closed is False


def test_alpha_vantage_source_skips_unsupported_ticker_before_request() -> None:
    from aqp.data.ingestion import AlphaVantageSource

    class _Timeseries:
        def daily_adjusted(self, symbol: str, outputsize: str):  # pragma: no cover
            raise AssertionError(f"unexpected provider call for {symbol}:{outputsize}")

    class _Client:
        timeseries = _Timeseries()

        def close(self):  # pragma: no cover
            return None

    source = AlphaVantageSource(client=_Client())

    frame = source.fetch(["AOK:BAT.BATS"], "2024-01-01", "2024-01-03", "1d")

    assert frame.empty


def test_alpha_vantage_source_can_keep_owned_client_open() -> None:
    from types import SimpleNamespace

    from aqp.data.ingestion import AlphaVantageSource

    clients: list[object] = []

    class _Timeseries:
        def daily_adjusted(self, symbol: str, outputsize: str):  # noqa: ARG002
            return SimpleNamespace(
                bars=[
                    {
                        "timestamp": "2024-01-02",
                        "open": "1",
                        "high": "2",
                        "low": "1",
                        "close": "2",
                        "volume": "100",
                    }
                ]
            )

    class _Client:
        timeseries = _Timeseries()
        closed = False

        def __init__(self, api_key=None):  # noqa: ARG002
            clients.append(self)

        def close(self):
            self.closed = True

    original_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "aqp.data.sources.alpha_vantage":
            return SimpleNamespace(AlphaVantageClient=_Client)
        return original_import(name, *args, **kwargs)

    import builtins

    old_import = builtins.__import__
    builtins.__import__ = fake_import
    try:
        source = AlphaVantageSource(close_after_fetch=False)
        source.fetch(["AAPL.NASDAQ"], "2024-01-01", "2024-01-03", "1d")
        source.fetch(["MSFT.NASDAQ"], "2024-01-01", "2024-01-03", "1d")
        source.close()
    finally:
        builtins.__import__ = old_import

    assert len(clients) == 1
    assert clients[0].closed is True
