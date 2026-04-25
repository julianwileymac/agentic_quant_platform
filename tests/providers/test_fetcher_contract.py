"""Contract tests for the ``Fetcher`` + ``QueryParams`` + ``Data`` triad."""
from __future__ import annotations

from typing import Any

import pytest

from aqp.providers.base import CostTier, Data, Fetcher, QueryParams
from aqp.providers.catalog import (
    fetcher_catalog,
    pick_fetcher,
    register_fetcher,
)


class DemoQueryParams(QueryParams):
    symbol: str
    limit: int = 10


class DemoData(Data):
    symbol: str
    value: float


class DemoFetcher(Fetcher[DemoQueryParams, list[DemoData]]):
    vendor_key = "demo"
    cost_tier = CostTier.FREE
    description = "In-memory demo fetcher."
    require_credentials = False

    @staticmethod
    def transform_query(params: dict[str, Any]) -> DemoQueryParams:
        return DemoQueryParams(**params)

    @staticmethod
    def extract_data(query: DemoQueryParams, credentials):
        return [{"symbol": query.symbol, "value": float(i)} for i in range(query.limit)]

    @staticmethod
    def transform_data(query: DemoQueryParams, data, **kw) -> list[DemoData]:
        return [DemoData(**row) for row in data]


class AlternateFetcher(Fetcher[DemoQueryParams, list[DemoData]]):
    vendor_key = "alt"
    cost_tier = CostTier.PAID

    @staticmethod
    def transform_query(params): return DemoQueryParams(**params)

    @staticmethod
    def extract_data(query, credentials): return [{"symbol": query.symbol, "value": 99.0}]

    @staticmethod
    def transform_data(query, data, **kw): return [DemoData(**row) for row in data]


def test_fetcher_introspection():
    # classproperties should resolve through __orig_bases__.
    assert DemoFetcher.query_params_type is DemoQueryParams


def test_fetcher_describe():
    desc = DemoFetcher.describe()
    assert desc["vendor_key"] == "demo"
    assert desc["cost_tier"] == "free"
    assert desc["require_credentials"] is False


def test_fetcher_fetch_sync_extract():
    result = DemoFetcher.fetch({"symbol": "AAPL", "limit": 3})
    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(r, DemoData) for r in result)
    assert result[0].symbol == "AAPL"


def test_query_params_alias_dict():
    class _QP(QueryParams):
        # Map Python attribute ``symbol`` to provider-native name ``ticker``.
        __alias_dict__ = {"symbol": "ticker"}
        symbol: str

    qp = _QP(symbol="AAPL")
    dumped = qp.model_dump()
    # model_dump swaps Python field name → provider-native alias.
    assert "ticker" in dumped
    assert dumped["ticker"] == "AAPL"
    assert "symbol" not in dumped


def test_data_extra_fields_preserved():
    d = DemoData(symbol="AAPL", value=1.0, provider_specific="extra")
    assert d.symbol == "AAPL"
    assert getattr(d, "provider_specific") == "extra"


def test_catalog_register_and_pick():
    register_fetcher("demo.rows", DemoFetcher, priority=5)
    register_fetcher("demo.rows", AlternateFetcher, priority=1)

    primary = fetcher_catalog().primary("demo.rows")
    assert primary is DemoFetcher

    by_vendor = pick_fetcher("demo.rows", vendor="alt")
    assert by_vendor is AlternateFetcher

    by_cost = pick_fetcher("demo.rows", max_cost_tier=CostTier.FREE)
    assert by_cost is DemoFetcher


def test_catalog_describe_stable():
    register_fetcher("demo.rows", DemoFetcher, priority=5)
    describe = fetcher_catalog().describe()
    assert "demo.rows" in describe
    assert all("vendor_key" in row for row in describe["demo.rows"])


def test_catalog_fanout_collects_results_and_errors():
    register_fetcher("demo.fanout", DemoFetcher, priority=5)

    class FailingFetcher(Fetcher[DemoQueryParams, list[DemoData]]):
        vendor_key = "failing"
        cost_tier = CostTier.PAID

        @staticmethod
        def transform_query(params): return DemoQueryParams(**params)

        @staticmethod
        def extract_data(query, credentials): raise RuntimeError("boom")

        @staticmethod
        def transform_data(query, data, **kw): return []

    register_fetcher("demo.fanout", FailingFetcher, priority=3)

    results = list(fetcher_catalog().fanout("demo.fanout", {"symbol": "X", "limit": 1}))
    assert len(results) == 2
    # Demo succeeds, failing surfaces an exception.
    ok = [r for r in results if r[2] is None]
    err = [r for r in results if r[2] is not None]
    assert len(ok) == 1
    assert len(err) == 1
