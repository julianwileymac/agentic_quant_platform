"""Tests for the typed identifier value objects + IdentifierSet/Scheme."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from aqp.core.domain.identifiers import (
    AccountId,
    ClientOrderId,
    IdentifierScheme,
    IdentifierSet,
    IdentifierValue,
    InstrumentId,
    StrategyId,
    Symbol2,
    TradeId,
    Venue,
)


def test_id_immutable_and_hashable():
    v = Venue("NASDAQ")
    assert str(v) == "NASDAQ"
    assert v == Venue("NASDAQ")
    assert v != Venue("NYSE")
    assert hash(v) == hash(Venue("NASDAQ"))


def test_empty_id_rejected():
    with pytest.raises(ValueError):
        Venue("")


def test_instrument_id_vt_symbol_roundtrip():
    iid = InstrumentId.from_str("AAPL.NASDAQ")
    assert iid.symbol == Symbol2("AAPL")
    assert iid.venue == Venue("NASDAQ")
    assert iid.vt_symbol == "AAPL.NASDAQ"
    assert str(iid) == "AAPL.NASDAQ"


def test_instrument_id_from_parts():
    iid = InstrumentId.from_parts("MSFT", "NASDAQ")
    assert iid.vt_symbol == "MSFT.NASDAQ"


def test_instrument_id_default_venue():
    iid = InstrumentId.from_str("LOCAL_SYM")
    assert iid.venue == Venue("LOCAL")


def test_typed_ids_are_distinct():
    # Same raw string, different types → different objects.
    account = AccountId("ABC-123")
    strategy = StrategyId("ABC-123")
    # Dataclass equality compares type + fields
    assert account != strategy


def test_identifier_scheme_coverage():
    # Every documented identifier taxonomy should be enumerable.
    for key in ("TICKER", "CIK", "CUSIP", "ISIN", "FIGI", "LEI", "SEDOL", "GVKEY"):
        assert hasattr(IdentifierScheme, key)


def test_identifier_set_basic():
    iset = IdentifierSet()
    iset.add(IdentifierValue(scheme=IdentifierScheme.CUSIP, value="037833100"))
    iset.add(IdentifierValue(scheme=IdentifierScheme.CIK, value="320193"))
    iset.add(IdentifierValue(scheme=IdentifierScheme.ISIN, value="US0378331005"))
    assert len(iset) == 3
    assert iset.value_of(IdentifierScheme.CUSIP) == "037833100"
    assert iset.value_of(IdentifierScheme.CIK) == "320193"
    assert IdentifierScheme.ISIN in iset
    assert IdentifierScheme.SEDOL not in iset


def test_identifier_set_from_list_roundtrip():
    rows = [
        {"scheme": "cusip", "value": "037833100", "confidence": 1.0},
        {"scheme": "cik", "value": "320193", "confidence": 0.9},
    ]
    iset = IdentifierSet.from_list(rows)
    assert len(iset) == 2
    assert iset.value_of("cusip") == "037833100"
    out = iset.as_list()
    assert out[0]["scheme"] == "cusip"


def test_identifier_active_window():
    now = datetime.utcnow()
    past = now - timedelta(days=365)
    future = now + timedelta(days=30)
    expired = IdentifierValue(
        scheme=IdentifierScheme.TICKER,
        value="OLD",
        valid_from=past - timedelta(days=30),
        valid_to=past,
    )
    active = IdentifierValue(
        scheme=IdentifierScheme.TICKER,
        value="NEW",
        valid_from=past,
        valid_to=future,
    )
    assert expired.is_active(past - timedelta(days=1))
    assert not expired.is_active(now)
    assert active.is_active(now)


def test_identifier_primary_of_picks_highest_confidence():
    iset = IdentifierSet()
    iset.add(IdentifierValue(scheme=IdentifierScheme.TICKER, value="A", confidence=0.5))
    iset.add(IdentifierValue(scheme=IdentifierScheme.TICKER, value="B", confidence=0.9))
    iset.add(IdentifierValue(scheme=IdentifierScheme.TICKER, value="C", confidence=0.7))
    primary = iset.primary_of(IdentifierScheme.TICKER)
    assert primary is not None
    assert primary.value == "B"


def test_identifier_merge_deduplicates():
    a = IdentifierSet(values=[
        IdentifierValue(scheme=IdentifierScheme.CIK, value="1"),
        IdentifierValue(scheme=IdentifierScheme.ISIN, value="XXX"),
    ])
    b = IdentifierSet(values=[
        IdentifierValue(scheme=IdentifierScheme.CIK, value="1"),  # duplicate
        IdentifierValue(scheme=IdentifierScheme.LEI, value="LEI123"),
    ])
    merged = a.merge(b)
    assert len(merged) == 3
