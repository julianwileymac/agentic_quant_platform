"""Tests for the Phase 3 reconciliation state map.

The state map is the keystone of the Nautilus-#4012 fix: keying state
by ``(account_id, venue, vt_symbol, position_side)`` instead of
instrument id alone. These tests exercise that composite key.
"""
from __future__ import annotations

from datetime import datetime

from aqp.trading.reconciliation.state import (
    CachePositionSnapshot,
    CompositeKey,
    PositionStatusReport,
    ReconciliationStateMap,
)


def _cache(
    *,
    account_id: str = "alpaca-paper-1",
    venue: str = "alpaca",
    vt_symbol: str = "AAPL.NASDAQ",
    position_side: str = "net",
    quantity: float = 10.0,
) -> CachePositionSnapshot:
    return CachePositionSnapshot(
        account_id=account_id,
        venue=venue,
        vt_symbol=vt_symbol,
        position_side=position_side,
        quantity=quantity,
    )


def _venue(
    *,
    account_id: str = "alpaca-paper-1",
    venue: str = "alpaca",
    vt_symbol: str = "AAPL.NASDAQ",
    position_side: str = "net",
    quantity: float = 10.0,
) -> PositionStatusReport:
    return PositionStatusReport(
        account_id=account_id,
        venue=venue,
        vt_symbol=vt_symbol,
        position_side=position_side,
        quantity=quantity,
        snapshot_ts=datetime.utcnow(),
    )


def test_composite_key_is_hashable_and_equal():
    a = CompositeKey("alpaca-paper-1", "alpaca", "AAPL.NASDAQ", "net")
    b = CompositeKey("alpaca-paper-1", "alpaca", "AAPL.NASDAQ", "net")
    assert a == b
    assert hash(a) == hash(b)


def test_same_instrument_two_accounts_yields_distinct_keys():
    """Closes Nautilus #4012: account scoping disambiguates the key."""
    k1 = _cache(account_id="alpaca-1").key()
    k2 = _cache(account_id="alpaca-2").key()
    assert k1 != k2


def test_hedge_mode_long_short_yield_distinct_keys():
    """Hedge-mode venues carry LONG and SHORT as separate rows."""
    long_key = _cache(position_side="long").key()
    short_key = _cache(position_side="short").key()
    assert long_key != short_key
    assert long_key.position_side == "long"
    assert short_key.position_side == "short"


def test_state_map_indexes_by_composite_key():
    m = ReconciliationStateMap()
    cache = _cache(quantity=10.0)
    m[cache.key()] = cache
    assert cache.key() in m
    assert m.get(cache.key()).quantity == 10.0


def test_state_map_iterates_in_sorted_order():
    m = ReconciliationStateMap()
    c1 = _cache(vt_symbol="MSFT.NASDAQ")
    c2 = _cache(vt_symbol="AAPL.NASDAQ")
    c3 = _cache(vt_symbol="TSLA.NASDAQ")
    m[c1.key()] = c1
    m[c2.key()] = c2
    m[c3.key()] = c3
    symbols = [k.vt_symbol for k in m]
    assert symbols == ["AAPL.NASDAQ", "MSFT.NASDAQ", "TSLA.NASDAQ"]


def test_venue_report_and_cache_snapshot_share_same_key():
    """Venue + cache rows for the same position produce equal keys."""
    cache = _cache()
    venue = _venue()
    assert cache.key() == venue.key()


def test_default_position_side_is_net():
    """When the venue doesn't tell us, position_side defaults to 'net'."""
    report = PositionStatusReport(
        account_id="x",
        venue="y",
        vt_symbol="z",
        position_side="",  # empty -> normalized to 'net'
        quantity=1.0,
    )
    assert report.key().position_side == "net"


def test_state_map_distinguishes_same_symbol_across_venues():
    """A US AAPL position and a HKEX 9988 are NOT the same key."""
    us = _cache(venue="alpaca", vt_symbol="AAPL.NASDAQ").key()
    hk = _cache(venue="hkex", vt_symbol="9988.HKEX").key()
    assert us != hk
