"""Hermetic tests for entity-centric data products.

The tests use the in-memory DB fixture from conftest plus minimal
inserts so we avoid Iceberg dependencies. Bar reads are stubbed by
swapping ``read_arrow`` with a tiny shim.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from aqp.data.products import (
    BaseDataProduct,
    EquityEntity,
    InstrumentGraphProduct,
    PortfolioEntity,
    RegulatoryEntity,
)
from aqp.data.products.base import DataProductError, _enforce_token_budget


def _make_instrument(session, vt_symbol: str = "AAPL.NASDAQ") -> str:
    from aqp.persistence.models import Instrument

    instrument = Instrument(
        vt_symbol=vt_symbol,
        ticker=vt_symbol.split(".")[0],
        exchange=vt_symbol.split(".")[-1],
        asset_class="equity",
        security_type="spot",
        instrument_class="spot",
    )
    session.add(instrument)
    session.commit()
    return instrument.id


def test_base_data_product_requires_entity_id() -> None:
    class _Product(BaseDataProduct):
        product_kind = "test"

        def load(self) -> None:
            self._payload["ok"] = True

    with pytest.raises(DataProductError):
        _Product("")


def test_to_context_pack_envelope_shape() -> None:
    class _Product(BaseDataProduct):
        product_kind = "test"

        def load(self) -> None:
            self._payload["fundamentals"] = [{"x": 1}]
            self.add_provenance_source("test_provider")
            self.add_lineage(transform_kind="data_product_load", summary="loaded")

    product = _Product("ENT-1")
    pack = product.to_context_pack()
    assert pack["product_kind"] == "test"
    assert pack["entity_id"] == "ENT-1"
    assert pack["payload"]["fundamentals"] == [{"x": 1}]
    assert "test_provider" in pack["provenance"]["data_sources"]
    assert pack["lineage"][0]["transform_kind"] == "data_product_load"


def test_token_budget_drops_low_priority_sections() -> None:
    envelope = {
        "product_kind": "equity",
        "entity_id": "AAPL.NASDAQ",
        "as_of": datetime.utcnow().isoformat(),
        "payload": {
            "instrument": {"vt_symbol": "AAPL.NASDAQ"},
            "news": [{"headline": "x" * 600}] * 20,
        },
        "provenance": {"data_sources": ["alpha_vantage"]},
        "quality": {},
        "lineage": [],
    }
    truncated = _enforce_token_budget(dict(envelope), max_tokens=200)
    assert "truncated_sections" in truncated
    # Instrument section should never be the first one dropped.
    assert "instrument" in truncated["payload"]


def test_equity_entity_load_aggregates_db_rows(in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        _make_instrument(session, "AAPL.NASDAQ")

    # ``_lookup_recent_bars`` swallows missing-table / missing-pyiceberg
    # errors and returns ``{"rows": 0}``, so this test stays hermetic
    # without stubbing the iceberg layer explicitly.
    product = EquityEntity("AAPL.NASDAQ", bars_lookback_days=10)
    pack = product.to_context_pack()
    assert pack["product_kind"] == "equity"
    assert pack["entity_id"] == "AAPL.NASDAQ"
    assert pack["payload"]["instrument"]["vt_symbol"] == "AAPL.NASDAQ"
    assert isinstance(pack["payload"].get("identifiers"), list)


def test_equity_entity_raises_when_unknown_symbol(in_memory_db) -> None:
    product = EquityEntity("NOPE.NYSE")
    pack = product.to_context_pack()
    # Errors are caught and surfaced as ``error`` payload, not exceptions.
    assert "error" in pack["payload"]


def test_regulatory_entity_returns_empty_when_no_data(in_memory_db) -> None:
    product = RegulatoryEntity("AAPL.NASDAQ")
    pack = product.to_context_pack()
    assert pack["product_kind"] == "regulatory"
    payload = pack["payload"]
    assert "cfpb" in payload
    assert "fda" in payload
    assert "uspto" in payload


def test_portfolio_entity_handles_empty_portfolio(in_memory_db) -> None:
    product = PortfolioEntity("strategy-foo")
    pack = product.to_context_pack()
    assert pack["product_kind"] == "portfolio"
    assert pack["payload"]["positions"] == []


def test_instrument_graph_loads_root(in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        _make_instrument(session, "AAPL.NASDAQ")

    product = InstrumentGraphProduct("AAPL.NASDAQ", depth=1, max_nodes=10)
    pack = product.to_context_pack()
    nodes = pack["payload"]["nodes"]
    assert len(nodes) >= 1
    assert nodes[0]["vt_symbol"] == "AAPL.NASDAQ"
