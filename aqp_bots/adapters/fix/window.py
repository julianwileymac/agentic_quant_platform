"""Venue-specific FIX ResendRequest window caps.

Per blueprint Caveat #8: every venue has a hard ceiling on the size of
a ``ResendRequest(35=2)`` window. Exceeding it triggers a Session Level
Reject; the adapter must paginate.

Documented from venue specs:

- **CME iLink**: 2500 messages per request. From CME docs:
  "tag 58-Text: Range of messages to resend is greater than maximum
  allowed 2500" — hard limit enforced by a Session Level Reject(35=3).

- **Trading Technologies (TT)**: 720 hours (~30 days) for accounts
  with <250 users; 168 hours (~7 days) for accounts with >=250 users.

- **ICE**: 24-hour rolling window per session.

Defaults shipped here are conservative; venue adapters may override
via :func:`set_venue_window`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ResendWindow:
    """How big a ResendRequest a venue accepts."""

    venue: str
    max_messages: int | None = None
    max_age_hours: int | None = None
    notes: str = ""


VENUE_RESEND_WINDOWS: dict[str, ResendWindow] = {
    "cme": ResendWindow(
        venue="cme",
        max_messages=2500,
        notes="iLink: Session Level Reject if range > 2500 messages",
    ),
    "tt_small": ResendWindow(
        venue="tt_small",
        max_age_hours=720,
        notes="Trading Technologies, account <250 users",
    ),
    "tt_large": ResendWindow(
        venue="tt_large",
        max_age_hours=168,
        notes="Trading Technologies, account >=250 users",
    ),
    "ice": ResendWindow(
        venue="ice",
        max_age_hours=24,
        notes="ICE: rolling 24-hour window per session",
    ),
    "default": ResendWindow(
        venue="default",
        max_messages=1000,
        notes="Conservative default for unlisted venues",
    ),
}


def resend_window_for(venue: str) -> ResendWindow:
    """Return the resend window for ``venue`` (default if unknown)."""
    return VENUE_RESEND_WINDOWS.get(venue.lower(), VENUE_RESEND_WINDOWS["default"])


def set_venue_window(venue: str, window: ResendWindow) -> None:
    """Override the window for ``venue``."""
    VENUE_RESEND_WINDOWS[venue.lower()] = window


__all__ = [
    "VENUE_RESEND_WINDOWS",
    "ResendWindow",
    "resend_window_for",
    "set_venue_window",
]
