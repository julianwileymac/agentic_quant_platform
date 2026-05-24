"""Phase 3: FIX venue resend windows (CME 2500-message cap, TT 720h/168h)."""
from __future__ import annotations

from aqp_bots.adapters.fix.window import (
    VENUE_RESEND_WINDOWS,
    ResendWindow,
    resend_window_for,
    set_venue_window,
)


def test_cme_window_has_2500_message_cap() -> None:
    win = resend_window_for("cme")
    assert win.venue == "cme"
    assert win.max_messages == 2500


def test_tt_small_window_720_hours() -> None:
    win = resend_window_for("tt_small")
    assert win.max_age_hours == 720


def test_tt_large_window_168_hours() -> None:
    win = resend_window_for("tt_large")
    assert win.max_age_hours == 168


def test_unknown_venue_falls_back_to_default() -> None:
    win = resend_window_for("nonexistent")
    assert win.venue == "default"
    assert win.max_messages == 1000


def test_set_venue_window_overrides() -> None:
    set_venue_window(
        "scratch",
        ResendWindow(venue="scratch", max_messages=42, notes="test override"),
    )
    assert resend_window_for("scratch").max_messages == 42
