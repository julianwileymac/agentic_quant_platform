from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def test_alpha_vantage_history_appends_arrow_and_registers_lineage(monkeypatch):
    from aqp.data.sources.alpha_vantage import history as history_mod
    from aqp.data.sources.alpha_vantage.history import (
        AlphaVantageHistoryPipeline,
        AlphaVantageHistoryRequest,
    )

    appended = {}
    registered = {}

    def _append(identifier, table, **kwargs):
        appended["identifier"] = identifier
        appended["rows"] = table.num_rows
        appended["schema"] = table.schema
        appended["kwargs"] = kwargs
        return object()

    def _register(**kwargs):
        registered.update(kwargs)
        return {"dataset_version_id": "version-1"}

    class _Timeseries:
        def daily_adjusted(self, symbol, **kwargs):  # noqa: ARG002
            return SimpleNamespace(
                bars=[
                    {
                        "timestamp": "2024-01-02",
                        "open": "100",
                        "high": "110",
                        "low": "99",
                        "close": "105",
                        "adjusted_close": "104",
                        "volume": "12345",
                    }
                ]
            )

    class _Client:
        timeseries = _Timeseries()

    monkeypatch.setattr(history_mod.iceberg_catalog, "append_arrow", _append)
    monkeypatch.setattr(history_mod, "register_dataset_version", _register)

    result = AlphaVantageHistoryPipeline(client=_Client()).run(
        AlphaVantageHistoryRequest(
            symbols=["AAPL.NASDAQ"],
            start="2024-01-01",
            end="2024-01-31",
            namespace="aqp_test",
            table="bars",
        )
    )

    assert result.rows_written == 1
    assert appended["identifier"] == "aqp_test.bars"
    assert appended["rows"] == 1
    assert str(appended["schema"].field("timestamp").type) == "timestamp[us]"
    assert registered["iceberg_identifier"] == "aqp_test.bars"
    assert registered["domain"] == "market.bars"


def test_alpha_vantage_history_intraday_coerces_invalid_interval(monkeypatch):
    """Invalid UI intervals (e.g. 1d) must not be sent to TIME_SERIES_INTRADAY."""
    from aqp.data.sources.alpha_vantage import history as history_mod
    from aqp.data.sources.alpha_vantage.history import (
        AlphaVantageHistoryPipeline,
        AlphaVantageHistoryRequest,
    )

    captured: dict[str, Any] = {}

    class _Timeseries:
        def intraday(self, symbol, **kwargs):  # noqa: ARG002
            captured.update(kwargs)
            return SimpleNamespace(bars=[])

    class _Client:
        timeseries = _Timeseries()

    monkeypatch.setattr(history_mod.iceberg_catalog, "append_arrow", lambda *a, **k: None)
    monkeypatch.setattr(history_mod, "register_dataset_version", lambda **k: {})

    AlphaVantageHistoryPipeline(client=_Client()).run(
        AlphaVantageHistoryRequest(
            symbols=["IBM.NASDAQ"],
            function="intraday",
            interval="1d",
            namespace="aqp_test",
            table="bars",
        )
    )
    assert captured.get("interval") == "5min"
