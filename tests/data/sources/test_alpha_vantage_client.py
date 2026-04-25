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
    from aqp.data.sources.alpha_vantage import load_api_key
    from aqp.data.sources.alpha_vantage import _credentials

    monkeypatch.setattr(_credentials.settings, "alpha_vantage_api_key", "")
    monkeypatch.setattr(_credentials.settings, "alpha_vantage_api_key_file", "")
    monkeypatch.delenv("AQP_ALPHA_VANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)

    assert load_api_key(strict=False, extra_paths=[]) == ""


def test_payload_error_classification() -> None:
    from aqp.data.sources.alpha_vantage._errors import RateLimitError, classify_payload

    err = classify_payload({"Note": "Thank you for using Alpha Vantage! Our standard API rate limit is reached."})
    assert isinstance(err, RateLimitError)


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
