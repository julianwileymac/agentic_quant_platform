"""Unit tests for IBKR historical service logic."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import pandas as pd
import pytest

from aqp.data.ibkr_historical import (
    IBKRHistoricalPacingError,
    IBKRHistoricalService,
    IBKRHistoricalTimeoutError,
    IBKRHistoricalUnavailableError,
    IBKRHistoricalValidationError,
    _check_and_record_pacing,
    _duration_to_timedelta,
    _validate_duration_for_bar_size,
)


@pytest.fixture(autouse=True)
def _reset_pacing_state() -> None:
    IBKRHistoricalService._pacing_entries.clear()


@pytest.mark.asyncio
async def test_fetch_bars_returns_canonical_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeStock:
        def __init__(self, symbol: str, exchange: str, currency: str) -> None:
            self.symbol = symbol
            self.exchange = exchange
            self.currency = currency
            self.secType = "STK"
            self.primaryExchange = ""

    class _Detail:
        def __init__(self, contract: Any) -> None:
            self.contract = contract

    class _Bar:
        def __init__(self, date: int, o: float, h: float, l: float, c: float, v: float) -> None:
            self.date = date
            self.open = o
            self.high = h
            self.low = l
            self.close = c
            self.volume = v

    class _FakeIB:
        def __init__(self) -> None:
            self._connected = False

        async def connectAsync(self, *_a: Any, **_k: Any) -> None:
            self._connected = True

        def reqMarketDataType(self, *_a: Any, **_k: Any) -> None:
            return None

        async def reqContractDetailsAsync(self, contract: Any) -> list[Any]:
            return [_Detail(contract)]

        async def reqHistoricalDataAsync(self, **_kwargs: Any) -> list[Any]:
            return [
                _Bar(int(pd.Timestamp("2024-01-02 00:00:00").timestamp()), 100, 101, 99, 100.5, 1000),
                _Bar(int(pd.Timestamp("2024-01-03 00:00:00").timestamp()), 101, 102, 100, 101.5, 1200),
            ]

        def isConnected(self) -> bool:
            return self._connected

        def disconnect(self) -> None:
            self._connected = False

    monkeypatch.setattr(
        "aqp.data.ibkr_historical._load_ib_components",
        lambda: (_FakeIB, _FakeStock),
    )

    svc = IBKRHistoricalService(max_requests=3)
    out = await svc.fetch_bars(
        vt_symbol="AAPL.NASDAQ",
        start="2024-01-01",
        end="2024-01-05",
        bar_size="1 day",
        what_to_show="TRADES",
        use_rth=True,
    )
    assert not out.empty
    assert out.columns.tolist() == [
        "timestamp",
        "vt_symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    assert out["vt_symbol"].unique().tolist() == ["AAPL.NASDAQ"]
    assert len(out) == 2


def test_duration_validation_rejects_invalid_step_size() -> None:
    with pytest.raises(IBKRHistoricalValidationError):
        _validate_duration_for_bar_size("5000 S", "1 day")


def test_pacing_guard_rejects_identical_request_within_15_seconds() -> None:
    _check_and_record_pacing(signature="sig-1", contract_key="AAPL|SMART|TRADES", weight=1)
    with pytest.raises(IBKRHistoricalPacingError):
        _check_and_record_pacing(signature="sig-1", contract_key="AAPL|SMART|TRADES", weight=1)


@pytest.mark.asyncio
async def test_fetch_bars_rejects_unsupported_what_to_show() -> None:
    svc = IBKRHistoricalService()
    with pytest.raises(IBKRHistoricalValidationError):
        await svc.fetch_bars(
            vt_symbol="AAPL.NASDAQ",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 10),
            what_to_show="ADJUSTED_LAST",
        )


# ---------------------------------------------------------------------------
# Hardening: relativedelta math, retry-on-timeout, availability probe.
# ---------------------------------------------------------------------------


def test_duration_math_uses_calendar_months_for_february() -> None:
    # Feb 2024 has 29 days; rough 30-day math would over-subtract.
    anchor = datetime(2024, 3, 1)
    delta = _duration_to_timedelta("1 M", anchor=anchor)
    assert delta.days == 29  # Feb 2024 length


def test_duration_math_uses_calendar_years() -> None:
    # 2024 is a leap year so ``1 Y`` from 2025-01-01 should be 366 days.
    anchor = datetime(2025, 1, 1)
    delta = _duration_to_timedelta("1 Y", anchor=anchor)
    assert delta.days == 366


def test_duration_math_days_still_exact() -> None:
    delta = _duration_to_timedelta("7 D")
    assert delta.days == 7


@pytest.mark.asyncio
async def test_fetch_bars_retries_on_timeout_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """One transient TimeoutError should be absorbed; bars still returned."""

    class _FakeStock:
        def __init__(self, symbol: str, exchange: str, currency: str) -> None:
            self.symbol = symbol
            self.exchange = exchange
            self.currency = currency
            self.secType = "STK"
            self.primaryExchange = ""

    class _Detail:
        def __init__(self, contract: Any) -> None:
            self.contract = contract

    class _Bar:
        def __init__(self, date: int) -> None:
            self.date = date
            self.open = 100.0
            self.high = 101.0
            self.low = 99.0
            self.close = 100.5
            self.volume = 1000.0

    class _FakeIB:
        def __init__(self) -> None:
            self._connected = False
            self.hist_calls = 0

        async def connectAsync(self, *_a: Any, **_k: Any) -> None:
            self._connected = True

        def reqMarketDataType(self, *_a: Any, **_k: Any) -> None:
            return None

        async def reqContractDetailsAsync(self, contract: Any) -> list[Any]:
            return [_Detail(contract)]

        async def reqHistoricalDataAsync(self, **_kwargs: Any) -> list[Any]:
            self.hist_calls += 1
            if self.hist_calls == 1:
                raise asyncio.TimeoutError()
            return [_Bar(int(pd.Timestamp("2024-01-02").timestamp()))]

        def isConnected(self) -> bool:
            return self._connected

        def disconnect(self) -> None:
            self._connected = False

    fake_ib_instance = _FakeIB()

    def _load() -> tuple[type, type]:
        class _Factory:
            def __new__(cls, *args, **kwargs):  # noqa: ARG002
                return fake_ib_instance

        return _Factory, _FakeStock

    monkeypatch.setattr("aqp.data.ibkr_historical._load_ib_components", _load)

    svc = IBKRHistoricalService(retry_backoff_sec=0.0)
    out = await svc.fetch_bars(
        vt_symbol="AAPL.NASDAQ",
        start="2024-01-01",
        end="2024-01-05",
        bar_size="1 day",
    )
    assert fake_ib_instance.hist_calls == 2
    assert not out.empty


@pytest.mark.asyncio
async def test_fetch_bars_raises_timeout_error_after_all_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStock:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            self.secType = "STK"
            self.primaryExchange = ""

    class _Detail:
        def __init__(self, contract: Any) -> None:
            self.contract = contract

    class _FakeIB:
        def __init__(self) -> None:
            self._connected = False
            self.hist_calls = 0

        async def connectAsync(self, *_a: Any, **_k: Any) -> None:
            self._connected = True

        def reqMarketDataType(self, *_a: Any, **_k: Any) -> None:
            return None

        async def reqContractDetailsAsync(self, contract: Any) -> list[Any]:
            return [_Detail(contract)]

        async def reqHistoricalDataAsync(self, **_kwargs: Any) -> list[Any]:
            self.hist_calls += 1
            raise asyncio.TimeoutError()

        def isConnected(self) -> bool:
            return self._connected

        def disconnect(self) -> None:
            self._connected = False

    fake_ib_instance = _FakeIB()

    def _load() -> tuple[type, type]:
        class _Factory:
            def __new__(cls, *args, **kwargs):  # noqa: ARG002
                return fake_ib_instance

        return _Factory, _FakeStock

    monkeypatch.setattr("aqp.data.ibkr_historical._load_ib_components", _load)

    svc = IBKRHistoricalService(max_retries=1, retry_backoff_sec=0.0)
    with pytest.raises(IBKRHistoricalTimeoutError):
        await svc.fetch_bars(
            vt_symbol="AAPL.NASDAQ",
            start="2024-01-01",
            end="2024-01-05",
            bar_size="1 day",
        )
    assert fake_ib_instance.hist_calls == 2  # 1 attempt + 1 retry


def test_is_available_returns_false_when_socket_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    IBKRHistoricalService.clear_availability_cache()

    import socket

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise ConnectionRefusedError("tws offline")

    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(
        "aqp.data.ibkr_historical._load_ib_components",
        lambda: (object, object),
    )

    ok, msg = IBKRHistoricalService.is_available(host="127.0.0.1", port=7497, use_cache=False)
    assert ok is False
    assert "Cannot reach" in msg


def test_is_available_caches_result(monkeypatch: pytest.MonkeyPatch) -> None:
    IBKRHistoricalService.clear_availability_cache()

    calls = {"n": 0}

    class _FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args, **kwargs):
            return None

    def _connect(*_a: Any, **_k: Any) -> _FakeSocket:
        calls["n"] += 1
        return _FakeSocket()

    import socket

    monkeypatch.setattr(socket, "create_connection", _connect)
    monkeypatch.setattr(
        "aqp.data.ibkr_historical._load_ib_components",
        lambda: (object, object),
    )

    ok1, _ = IBKRHistoricalService.is_available(host="127.0.0.1", port=7497)
    ok2, _ = IBKRHistoricalService.is_available(host="127.0.0.1", port=7497)
    assert ok1 and ok2
    assert calls["n"] == 1  # cached


@pytest.mark.asyncio
async def test_fetch_bars_translates_connection_refused_to_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStock:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

    class _FakeIB:
        async def connectAsync(self, *_a: Any, **_k: Any) -> None:
            raise ConnectionRefusedError("refused")

        def isConnected(self) -> bool:
            return False

        def disconnect(self) -> None:
            return None

    monkeypatch.setattr(
        "aqp.data.ibkr_historical._load_ib_components",
        lambda: (_FakeIB, _FakeStock),
    )

    svc = IBKRHistoricalService()
    with pytest.raises(IBKRHistoricalUnavailableError):
        await svc.fetch_bars(
            vt_symbol="AAPL.NASDAQ",
            start="2024-01-01",
            end="2024-01-02",
            bar_size="1 day",
        )
