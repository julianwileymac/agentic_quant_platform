"""FIX 4.2 / 4.4 / 5.0 adapter family.

Built on `simplefix <https://github.com/da4089/simplefix>`_ for the
parser and a hand-rolled session layer for sequence-gap recovery.

Session-layer state machine (blueprint §G.5) implements the full
recovery contract:

- ``ResendRequest(35=2)`` with ``BeginSeqNo(7)`` set to first missing,
  ``EndSeqNo(16)=0`` ("all messages after").
- ``SequenceReset-GapFill(35=4, 123=Y)`` for admin/stale gap fills.
- ``PossDupFlag(43)=Y`` and ``PossResend(97)=Y`` handled (silently dropped
  when older than ``NextNumIn`` and no PossDupFlag).
- ``TestRequest(35=1)`` after ``TestRequestThreshold * HeartBtInt`` of
  silence. Threshold defaults to **1.5** (FIX spec recommended range
  1.2-2.0).
- ``Logout(35=5)`` with ``SessionStatus(1409)=9`` ("received MsgSeqNum
  too low") when inbound sequence is below expected and PossDupFlag
  is not Y.

Venue-specific resend window caps documented in :mod:`.window`:

- CME iLink: 2500-message ResendRequest cap (Session Level Reject).
- Trading Technologies: 720h (<250 accounts) / 168h (>=250 accounts).
"""
from __future__ import annotations

from aqp_bots.adapters.fix.session import (
    FixSequenceError,
    FixSessionConfig,
    FixSessionLayer,
)
from aqp_bots.adapters.fix.window import (
    VENUE_RESEND_WINDOWS,
    ResendWindow,
    resend_window_for,
)

__all__ = [
    "FixSequenceError",
    "FixSessionConfig",
    "FixSessionLayer",
    "VENUE_RESEND_WINDOWS",
    "ResendWindow",
    "resend_window_for",
]
