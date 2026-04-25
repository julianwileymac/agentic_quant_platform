"""Tests for the market-hours database."""
from __future__ import annotations

from datetime import UTC, datetime

from aqp.core.exchange_hours import default_database


def test_default_database_has_us_equities():
    db = default_database()
    assert "NASDAQ" in db
    assert "NYSE" in db
    assert "BINANCE" in db


def test_us_equities_closed_on_weekends():
    db = default_database()
    # 2026-04-25 is a Saturday.
    assert db.is_open("NASDAQ", datetime(2026, 4, 25, 14, 0, tzinfo=UTC)) is False


def test_us_equities_open_during_session():
    db = default_database()
    # 2026-04-22 is a Wednesday — market opens 09:30 ET = 13:30 UTC (standard) / 14:30 (DST).
    # Use 16:00 UTC which is safely after open.
    assert db.is_open("NASDAQ", datetime(2026, 4, 22, 16, 0, tzinfo=UTC))


def test_crypto_always_open():
    db = default_database()
    # 24x7 market should be open any random UTC time.
    assert db.is_open("BINANCE", datetime(2026, 4, 25, 14, 0, tzinfo=UTC))
    assert db.is_open("COINBASE", datetime(2026, 1, 1, 3, 0, tzinfo=UTC))


def test_next_open_returns_future_timestamp():
    db = default_database()
    now = datetime(2026, 4, 25, 14, 0, tzinfo=UTC)  # Saturday
    nxt = db.next_open("NASDAQ", now)
    assert nxt is not None
    assert nxt > now
