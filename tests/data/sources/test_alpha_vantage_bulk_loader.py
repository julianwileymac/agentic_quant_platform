from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd


class _Timeseries:
    def daily_adjusted(self, symbol: str, **kwargs: Any) -> Any:  # noqa: ARG002
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

    def daily(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError


class _Fundamentals:
    def overview(self, symbol: str) -> Any:  # noqa: ARG002
        return SimpleNamespace(model_dump=lambda: {"symbol": symbol, "Name": "Acme"})


class _Intelligence:
    pass


class _Technicals:
    pass


class _Client:
    timeseries = _Timeseries()
    fundamentals = _Fundamentals()
    intelligence = _Intelligence()
    technicals = _Technicals()

    def listing_status(self):
        return pd.DataFrame()

    def close(self) -> None:  # pragma: no cover
        return None


def test_bulk_loader_runs_filtered_selection(monkeypatch):
    from aqp.data.sources.alpha_vantage import bulk_loader as mod
    from aqp.data.sources.alpha_vantage.bulk_loader import (
        AlphaVantageBulkLoader,
    )

    appended: dict[str, Any] = {}
    registered: dict[str, Any] = {}
    data_links: list[Any] = []

    def _append(identifier, table, **kwargs):
        appended["identifier"] = identifier
        appended["rows"] = table.num_rows
        appended["partition_spec"] = kwargs.get("partition_spec")
        return object()

    def _register(**kwargs):
        registered.update(kwargs)
        return {"dataset_version_id": "ver-1"}

    class _FakeSession:
        def __init__(self):
            self.added = []

        def execute(self, *args, **kwargs):  # noqa: ARG002
            class _Result:
                def scalars(self_inner):
                    class _S:
                        def all(self_inner_inner):
                            return []

                    return _S()

            return _Result()

        def add(self, item):
            self.added.append(item)
            data_links.append(item)

        def flush(self):
            return None

    class _SessionCtx:
        def __enter__(self_inner):
            return _FakeSession()

        def __exit__(self_inner, *exc):  # noqa: ARG002
            return False

    monkeypatch.setattr(mod.iceberg_catalog, "append_arrow", _append)
    monkeypatch.setattr(mod, "register_dataset_version", _register)
    monkeypatch.setattr(mod, "get_session", lambda: _SessionCtx())

    loader = AlphaVantageBulkLoader(client=_Client())
    result = loader.run(
        endpoints=["timeseries.daily_adjusted"],
        symbols=["AAPL.NASDAQ", "MSFT.NASDAQ"],
        cache=False,
    )

    assert result.requested_symbols == 2
    assert result.total_rows == 2
    assert appended["identifier"] == "aqp_alpha_vantage.time_series_daily_adjusted"
    assert appended["rows"] == 2
    assert appended["partition_spec"]
    assert registered["iceberg_identifier"] == "aqp_alpha_vantage.time_series_daily_adjusted"
    assert len(data_links) == 2


def test_bulk_loader_resolves_all_active(monkeypatch):
    from aqp.data.sources.alpha_vantage import bulk_loader as mod

    class _Result:
        def scalars(self):
            class _S:
                def all(self):
                    return ["AAPL.NASDAQ", "MSFT.NASDAQ"]

            return _S()

    class _FakeSession:
        def execute(self, *args, **kwargs):  # noqa: ARG002
            return _Result()

    class _SessionCtx:
        def __enter__(self_inner):
            return _FakeSession()

        def __exit__(self_inner, *exc):  # noqa: ARG002
            return False

    monkeypatch.setattr(mod, "get_session", lambda: _SessionCtx())

    symbols = mod.resolve_symbols("all_active")
    assert symbols == ["AAPL.NASDAQ", "MSFT.NASDAQ"]
