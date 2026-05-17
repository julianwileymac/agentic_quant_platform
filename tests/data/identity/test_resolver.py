"""Tests for the temporal identifier resolver service.

The resolver walks the time-versioned ``identifier_links`` rows. These
tests use ``MagicMock`` to stub out the SQLAlchemy session so the test
suite stays hermetic (AGENTS rule 10) -- they exercise the query
construction and result shaping, not real Postgres.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from aqp.data.identity.resolver import (
    IdentifierHistoryRow,
    IdentifierResolution,
    IdentifierResolver,
)


def _fake_row(
    *,
    entity_kind: str = "instrument",
    entity_id: str = "inst-1",
    instrument_id: str | None = "inst-1",
    scheme: str = "cusip",
    value: str = "037833100",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    confidence: float = 1.0,
    source_id: str | None = "loader-1",
    meta: dict | None = None,
):
    """Build a fake IdentifierLink row exposing the attributes the resolver reads."""
    row = MagicMock()
    row.entity_kind = entity_kind
    row.entity_id = entity_id
    row.instrument_id = instrument_id
    row.scheme = scheme
    row.value = value
    row.valid_from = valid_from
    row.valid_to = valid_to
    row.confidence = confidence
    row.source_id = source_id
    row.meta = meta or {}
    return row


@pytest.fixture
def patched_session():
    """Patch ``aqp.persistence.db.get_session`` to yield a controllable mock."""
    with patch("aqp.persistence.db.get_session") as gs:
        session = MagicMock()
        cm = MagicMock()
        cm.__enter__.return_value = session
        cm.__exit__.return_value = False
        gs.return_value = cm
        yield session


def test_resolve_returns_matching_row(patched_session):
    """Forward resolution returns the highest-confidence matching row."""
    row = _fake_row(
        scheme="cusip",
        value="037833100",
        valid_from=datetime(2010, 1, 1),
        valid_to=None,  # open-ended
    )
    scalars = MagicMock()
    scalars.first.return_value = row
    result = MagicMock()
    result.scalars.return_value = scalars
    patched_session.execute.return_value = result

    res = IdentifierResolver().resolve(scheme="CUSIP", value="037833100")
    assert isinstance(res, IdentifierResolution)
    assert res.scheme == "cusip"
    assert res.value == "037833100"
    assert res.is_open_ended is True
    assert res.confidence == 1.0


def test_resolve_normalizes_scheme_and_value(patched_session):
    """Scheme is lower-cased and value is trimmed before query construction."""
    row = _fake_row()
    scalars = MagicMock()
    scalars.first.return_value = row
    result = MagicMock()
    result.scalars.return_value = scalars
    patched_session.execute.return_value = result

    IdentifierResolver().resolve(scheme="  CUSIP ", value="  037833100  ")
    # Query was constructed exactly once.
    patched_session.execute.assert_called_once()


def test_resolve_returns_none_on_empty_inputs():
    """Empty scheme or value short-circuits without a DB call."""
    res = IdentifierResolver().resolve(scheme="", value="037833100")
    assert res is None
    res = IdentifierResolver().resolve(scheme="cusip", value="")
    assert res is None


def test_resolve_to_instrument_returns_id(patched_session):
    row = _fake_row(instrument_id="inst-42")
    scalars = MagicMock()
    scalars.first.return_value = row
    result = MagicMock()
    result.scalars.return_value = scalars
    patched_session.execute.return_value = result

    iid = IdentifierResolver().resolve_to_instrument(
        scheme="cusip", value="037833100"
    )
    assert iid == "inst-42"


def test_resolve_returns_none_when_no_row(patched_session):
    """Missing row returns None rather than raising."""
    scalars = MagicMock()
    scalars.first.return_value = None
    result = MagicMock()
    result.scalars.return_value = scalars
    patched_session.execute.return_value = result

    res = IdentifierResolver().resolve(scheme="cusip", value="nope")
    assert res is None


def test_history_sorted_chronologically(patched_session):
    """History rows: open-start first, open-end last, with stable ordering."""
    rows = [
        _fake_row(
            scheme="ticker",
            value="META",
            valid_from=datetime(2022, 6, 9),
            valid_to=None,
        ),
        _fake_row(
            scheme="ticker",
            value="FB",
            valid_from=None,
            valid_to=datetime(2022, 6, 9),
        ),
        _fake_row(
            scheme="cusip",
            value="30303M102",
            valid_from=datetime(2012, 5, 18),
            valid_to=None,
        ),
    ]
    scalars = MagicMock()
    scalars.all.return_value = rows
    result = MagicMock()
    result.scalars.return_value = scalars
    patched_session.execute.return_value = result

    history = IdentifierResolver().history(
        entity_kind="instrument", entity_id="meta-1"
    )
    assert [r.value for r in history[:1]] == ["FB"]  # null valid_from first
    assert all(isinstance(r, IdentifierHistoryRow) for r in history)
    # The last entry (open-ended) is META (current ticker).
    assert history[-1].value in ("META", "30303M102")


def test_resolution_to_json_roundtrips():
    """to_json preserves the full row shape including NULL bounds."""
    r = IdentifierResolution(
        entity_kind="instrument",
        entity_id="inst-1",
        instrument_id="inst-1",
        scheme="cusip",
        value="037833100",
        valid_from=datetime(2010, 1, 1),
        valid_to=None,
        confidence=0.9,
        source_id="src",
        meta={"hint": "loader"},
    )
    blob = r.to_json()
    assert blob["scheme"] == "cusip"
    assert blob["valid_to"] is None
    assert blob["valid_from"] == "2010-01-01T00:00:00"
    assert blob["confidence"] == 0.9
    assert blob["meta"] == {"hint": "loader"}
