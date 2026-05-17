"""Tests for :class:`aqp.core.domain.options.OptionChainPayload`.

The payload validator must accept both columnar and record-form input,
emit canonical record form on serialize, and never drop rows when the
columnar shape has mis-aligned column lengths (the OpenBB-flagged
failure mode this class was built to close).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from aqp.core.domain.options import OptionChainPayload, OptionChainRecord


def test_columnar_input_zips_into_records():
    """Equal-length columnar input zips cleanly into per-row records."""
    payload = OptionChainPayload(
        underlying="AAPL",
        expiry=date(2026, 6, 19),
        strikes=[180.0, 185.0, 190.0],
        kinds=["call", "call", "call"],
        bid=[15.10, 11.20, 7.85],
        ask=[15.30, 11.40, 8.05],
        delta=[0.72, 0.61, 0.47],
        underlying_price=195.0,
    )
    assert len(payload.records) == 3
    assert payload.records[0].strike == 180.0
    assert payload.records[0].bid == 15.10
    assert payload.records[0].delta == 0.72
    assert payload.records[2].strike == 190.0


def test_record_input_passes_through():
    """Pre-zipped record form is left untouched."""
    payload = OptionChainPayload(
        underlying="AAPL",
        expiry=date(2026, 6, 19),
        records=[
            {"strike": 180.0, "expiry": date(2026, 6, 19), "kind": "call", "bid": 15.10},
            {"strike": 185.0, "expiry": date(2026, 6, 19), "kind": "put", "bid": 0.95},
        ],
    )
    assert len(payload.records) == 2
    assert payload.records[1].kind == "put"


def test_columnar_aliases_strikes_strike_expiries_expiry():
    """Both singular and plural column names are accepted."""
    payload = OptionChainPayload(
        underlying="AAPL",
        strike=[200.0, 205.0],
        expiry_dates_unused=None,  # noise key, should be ignored
        expiration=[date(2026, 6, 19), date(2026, 6, 19)],
        kind=["call", "put"],
        bid=[3.4, 5.2],
        ask=[3.6, 5.4],
    )
    assert len(payload.records) == 2
    assert payload.records[0].kind == "call"


def test_columnar_pads_shorter_arrays_with_none():
    """Mis-aligned columnar input pads shorter arrays with ``None``, never drops rows."""
    payload = OptionChainPayload(
        underlying="AAPL",
        strikes=[180.0, 185.0, 190.0],
        kinds=["call", "call", "call"],
        bid=[15.0, 11.0],  # short by 1 -- the third row gets bid=None
        expiry=date(2026, 6, 19),
    )
    assert len(payload.records) == 3
    assert payload.records[2].bid is None  # padded
    assert payload.records[2].strike == 190.0


def test_columnar_skips_rows_with_no_strike():
    """Rows where strike is missing (None) are dropped -- they're meaningless."""
    payload = OptionChainPayload(
        underlying="AAPL",
        strikes=[180.0, None, 190.0],
        kinds=["call", "call", "call"],
        expiry=date(2026, 6, 19),
    )
    # 2 rows survive (180 and 190), the middle one was dropped.
    assert len(payload.records) == 2


def test_serializer_emits_records_form():
    """Serialize always emits record form regardless of how data was loaded."""
    payload = OptionChainPayload(
        underlying="AAPL",
        expiry=date(2026, 6, 19),
        strikes=[180.0, 185.0],
        kinds=["call", "put"],
        bid=[15.10, 0.95],
    )
    dumped = payload.model_dump()
    assert "records" in dumped
    assert isinstance(dumped["records"], list)
    assert len(dumped["records"]) == 2
    # Columnar keys must NOT survive on output.
    assert "strikes" not in dumped
    assert "kinds" not in dumped


def test_to_arrow_record_batch_when_pyarrow_present():
    pa = pytest.importorskip("pyarrow")
    payload = OptionChainPayload(
        underlying="AAPL",
        expiry=date(2026, 6, 19),
        strikes=[180.0, 185.0],
        kinds=["call", "put"],
        bid=[15.10, 0.95],
        ask=[15.30, 1.05],
        delta=[0.72, -0.28],
    )
    batch = payload.to_arrow()
    assert isinstance(batch, pa.RecordBatch)
    assert batch.num_rows == 2
    schema_names = batch.schema.names
    for required in (
        "strike",
        "expiry",
        "kind",
        "bid",
        "ask",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
        "underlying_price",
        "ts_event",
    ):
        assert required in schema_names


def test_to_option_chain_lifts_to_legacy_dataclass():
    """``to_option_chain`` rebuilds the in-memory chain with Greeks attached."""
    payload = OptionChainPayload(
        underlying="AAPL",
        expiry=date(2026, 6, 19),
        strikes=[180.0, 185.0],
        kinds=["call", "put"],
        bid=[15.10, 0.95],
        ask=[15.30, 1.05],
        delta=[0.72, -0.28],
        gamma=[0.05, 0.05],
    )
    chain = payload.to_option_chain()
    assert chain.underlying == "AAPL"
    assert len(chain.slices) == 2
    # Greeks present on both slices.
    assert chain.slices[0].greeks is not None
    assert chain.slices[1].greeks is not None
    # Strikes round-trip.
    assert chain.slices[0].strike == pytest.approx(180.0)
    assert chain.slices[1].strike == pytest.approx(185.0)


def test_default_kind_is_call_when_missing():
    """Kind defaults to 'call' when not provided -- prevents silent column drops."""
    payload = OptionChainPayload(
        underlying="AAPL",
        strikes=[180.0],
        expiry=date(2026, 6, 19),
    )
    assert len(payload.records) == 1
    assert payload.records[0].kind == "call"
