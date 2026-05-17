from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from aqp.data.sources.alpha_vantage._errors import AlphaVantagePayloadError
from aqp.data.sources.alpha_vantage.coordination import (
    AlphaVantageHistoryCoordinationRequest,
    AlphaVantageIntradayCoordinationRequest,
    AlphaVantageRequestCoordinator,
)


@dataclass
class _Payload:
    bars: list[dict[str, Any]]


class _Timeseries:
    def __init__(self, *, bars: list[dict[str, Any]] | None = None, error: Exception | None = None) -> None:
        self.bars = bars or []
        self.error = error

    def daily_adjusted(self, ticker: str, **kwargs: Any) -> _Payload:
        del ticker, kwargs
        if self.error:
            raise self.error
        return _Payload(self.bars)

    def intraday(self, ticker: str, **kwargs: Any) -> _Payload:
        del ticker, kwargs
        if self.error:
            raise self.error
        return _Payload(self.bars)


class _Client:
    def __init__(self, timeseries: _Timeseries) -> None:
        self.timeseries = timeseries


def _bars() -> list[dict[str, Any]]:
    return [
        {
            "timestamp": "2026-05-01T14:30:00Z",
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "1000",
        },
        {
            "timestamp": "2026-05-01T14:31:00Z",
            "open": "100.5",
            "high": "102.0",
            "low": "100.0",
            "close": "101.5",
            "volume": "1100",
        },
    ]


def _patch_writes(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from aqp.data.sources.alpha_vantage import coordination as mod

    calls: dict[str, Any] = {"appends": [], "registrations": []}

    def _append(identifier: str, table: Any, **kwargs: Any) -> object:
        calls["appends"].append(
            {
                "identifier": identifier,
                "rows": table.num_rows,
                "kwargs": kwargs,
            }
        )
        return object()

    def _register(**kwargs: Any) -> dict[str, Any]:
        calls["registrations"].append(kwargs)
        return {"version": 1, "name": kwargs["name"]}

    monkeypatch.setattr(mod.iceberg_catalog, "append_arrow", _append)
    monkeypatch.setattr(mod.iceberg_catalog, "existing_keys_for_window", lambda *args, **kwargs: set())
    monkeypatch.setattr(mod, "register_dataset_version", _register)
    return calls


def test_history_coordinator_appends_and_emits_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_writes(monkeypatch)
    progress: list[tuple[str, str, dict[str, Any]]] = []
    coordinator = AlphaVantageRequestCoordinator(
        _Client(_Timeseries(bars=_bars())),
        progress_cb=lambda stage, message, extras: progress.append((stage, message, extras or {})),
    )

    result = coordinator.run_history(
        AlphaVantageHistoryCoordinationRequest(
            symbols=["IBM.NASDAQ"],
            iceberg_identifier="aqp_alpha_vantage.time_series_daily_adjusted",
            function="daily_adjusted",
            start="2026-05-01",
            end="2026-05-02",
        )
    )

    assert result.status == "completed"
    assert result.rows_written == 2
    assert result.symbols == ["IBM.NASDAQ"]
    assert calls["appends"][0]["rows"] == 2
    assert calls["registrations"][0]["name"] == "alpha_vantage.time_series_daily_adjusted"
    assert any(stage == "debug" and extras.get("ticker") == "IBM" for stage, _, extras in progress)
    assert any(extras.get("function_id") == "timeseries.daily_adjusted" for _, _, extras in progress)


def test_history_coordinator_records_provider_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_writes(monkeypatch)
    progress: list[tuple[str, str, dict[str, Any]]] = []
    coordinator = AlphaVantageRequestCoordinator(
        _Client(_Timeseries(error=AlphaVantagePayloadError("bad symbol"))),
        progress_cb=lambda stage, message, extras: progress.append((stage, message, extras or {})),
    )

    result = coordinator.run_history(
        AlphaVantageHistoryCoordinationRequest(
            symbols=["BAD.NASDAQ"],
            iceberg_identifier="aqp_alpha_vantage.time_series_daily_adjusted",
            function="daily_adjusted",
        )
    )

    assert result.status == "skipped"
    assert result.error == "no_successful_requests"
    assert result.errors == [{"ticker": "BAD", "vt_symbol": "BAD.NASDAQ", "error": "bad symbol"}]
    assert calls["appends"] == []
    assert any(stage == "warning" and extras.get("error") == "bad symbol" for stage, _, extras in progress)


def test_intraday_coordinator_deduplicates_existing_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_writes(monkeypatch)
    progress: list[tuple[str, str, dict[str, Any]]] = []

    from aqp.data.sources.alpha_vantage import coordination as mod

    def _existing_keys(identifier: str, *, symbols: list[str], time_min: Any, time_max: Any) -> set[tuple[str, Any]]:
        del identifier, time_max
        return {(symbols[0], time_min)}

    monkeypatch.setattr(mod.iceberg_catalog, "existing_keys_for_window", _existing_keys)
    coordinator = AlphaVantageRequestCoordinator(
        _Client(_Timeseries(bars=[_bars()[0]])),
        progress_cb=lambda stage, message, extras: progress.append((stage, message, extras or {})),
    )

    result = coordinator.run_intraday_component(
        AlphaVantageIntradayCoordinationRequest(
            component_id="IBM.NASDAQ:1min:2026-05",
            vt_symbol="IBM.NASDAQ",
            ticker="IBM",
            month="2026-05",
            interval="1min",
            iceberg_identifier="aqp_alpha_vantage.time_series_intraday",
        )
    )

    assert result.status == "skipped"
    assert result.error == "no_new_rows_after_dedup"
    assert result.fetched_rows == 1
    assert result.duplicate_rows == 1
    assert calls["appends"] == []
    assert any(extras.get("duplicate_rows") == 1 for _, _, extras in progress)


def test_intraday_coordinator_appends_new_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_writes(monkeypatch)
    progress: list[tuple[str, str, dict[str, Any]]] = []
    coordinator = AlphaVantageRequestCoordinator(
        _Client(_Timeseries(bars=_bars())),
        progress_cb=lambda stage, message, extras: progress.append((stage, message, extras or {})),
    )

    result = coordinator.run_intraday_component(
        AlphaVantageIntradayCoordinationRequest(
            component_id="IBM.NASDAQ:1min:2026-05",
            vt_symbol="IBM.NASDAQ",
            ticker="IBM",
            month="2026-05",
            interval="1min",
            iceberg_identifier="aqp_alpha_vantage.time_series_intraday",
        )
    )

    assert result.status == "completed"
    assert result.fetched_rows == 2
    assert result.rows_written == 2
    assert calls["appends"][0]["identifier"] == "aqp_alpha_vantage.time_series_intraday"
    assert calls["registrations"][0]["meta"]["request_component_id"] == "IBM.NASDAQ:1min:2026-05"
    assert any(extras.get("request_id") == "IBM.NASDAQ:1min:2026-05" for _, _, extras in progress)


def test_intraday_coordinator_reports_append_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_writes(monkeypatch)
    progress: list[tuple[str, str, dict[str, Any]]] = []

    from aqp.data.sources.alpha_vantage import coordination as mod

    def _append_failure(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("iceberg down")

    monkeypatch.setattr(mod.iceberg_catalog, "append_arrow", _append_failure)
    coordinator = AlphaVantageRequestCoordinator(
        _Client(_Timeseries(bars=_bars())),
        progress_cb=lambda stage, message, extras: progress.append((stage, message, extras or {})),
    )

    result = coordinator.run_intraday_component(
        AlphaVantageIntradayCoordinationRequest(
            component_id="IBM.NASDAQ:1min:2026-05",
            vt_symbol="IBM.NASDAQ",
            ticker="IBM",
            month="2026-05",
            interval="1min",
            iceberg_identifier="aqp_alpha_vantage.time_series_intraday",
        )
    )

    assert result.status == "failed"
    assert result.error == "iceberg down"
    assert any(stage == "error" and extras.get("error") == "iceberg down" for stage, _, extras in progress)
