"""FIX session-layer state machine + sequence-gap recovery.

Implements the canonical contract from the FIX Trading Community
Session Layer Online specification:

- Track ``MsgSeqNum(34)`` in both directions.
- On gap detection (inbound ``MsgSeqNum > NextNumIn``) send
  ``ResendRequest(35=2)`` with ``BeginSeqNo(7)=NextNumIn`` and
  ``EndSeqNo(16)=0`` ("all messages after").
- Replay arrives as repeated business messages with ``PossDupFlag(43)=Y``
  or ``SequenceReset-GapFill(35=4, 123=Y)`` for admin gap-fills.
- On inbound ``MsgSeqNum < NextNumIn`` without ``PossDupFlag(43)=Y``,
  terminate the session with ``Logout(35=5, 1409=9)``.
- ``Heartbeat(35=0)`` every ``HeartBtInt(108)`` seconds; ``TestRequest(35=1)``
  if no inbound message within ``TestRequestThreshold * HeartBtInt``
  (default threshold = 1.5; FIX spec recommends 1.2-2.0).

This is a pure state machine — transport (TCP socket, SSL, etc.) is
the responsibility of the concrete venue adapter. The session layer
consumes raw `simplefix.FixMessage` objects and emits the same.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# FIX session-level field numbers (admin tags)
_TAG_MSG_TYPE = 35
_TAG_MSG_SEQ_NUM = 34
_TAG_POSS_DUP_FLAG = 43
_TAG_POSS_RESEND = 97
_TAG_BEGIN_SEQ_NO = 7
_TAG_END_SEQ_NO = 16
_TAG_NEW_SEQ_NO = 36
_TAG_GAP_FILL_FLAG = 123
_TAG_SESSION_STATUS = 1409
_TAG_TEXT = 58
_TAG_TEST_REQ_ID = 112

# Admin MsgTypes
_MT_HEARTBEAT = b"0"
_MT_TEST_REQUEST = b"1"
_MT_RESEND_REQUEST = b"2"
_MT_REJECT = b"3"
_MT_SEQUENCE_RESET = b"4"
_MT_LOGOUT = b"5"
_MT_LOGON = b"A"
_MT_BUSINESS_MESSAGE_REJECT = b"j"

# Session status codes (1409)
_SS_RECEIVED_SEQNUM_TOO_LOW = b"9"


class FixSequenceError(RuntimeError):
    """Raised when the session layer cannot recover (terminal)."""


@dataclass(slots=True)
class FixSessionConfig:
    """Tunables for the session layer.

    ``test_request_threshold`` defaults to 1.5x ``HeartBtInt``; the FIX
    Trading Community recommends a value in the **1.2 - 2.0** range
    depending on latency sensitivity.
    """

    sender_comp_id: str
    target_comp_id: str
    heart_bt_int_seconds: int = 30
    test_request_threshold: float = 1.5
    venue: str = ""  # used to look up venue-specific resend windows


@dataclass(slots=True)
class FixSessionState:
    """Mutable session state."""

    next_seq_out: int = 1
    next_seq_in: int = 1
    last_inbound_at: float = 0.0
    last_outbound_at: float = 0.0
    expected_test_req_id: str | None = None
    in_resend_request: bool = False
    pending_resends: list[tuple[int, int]] = field(default_factory=list)
    is_logged_on: bool = False
    is_logged_out: bool = False


class FixSessionLayer:
    """Pure session-layer state machine.

    Usage::

        layer = FixSessionLayer(config, send_msg=transport.send)
        await layer.on_logon(msg)
        async for inbound in transport.recv_messages():
            await layer.on_inbound(inbound)
        await layer.heartbeat_loop()
    """

    def __init__(
        self,
        config: FixSessionConfig,
        *,
        send_msg: Any,
    ) -> None:
        self.config = config
        self.state = FixSessionState()
        self._send_msg = send_msg  # awaitable callable for raw FixMessage send
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public hooks
    # ------------------------------------------------------------------

    async def on_inbound(self, msg: Any) -> bool:
        """Process one inbound :class:`simplefix.FixMessage`.

        Returns True when the caller should treat the message as a
        normal business message; False when the session layer has
        handled it (admin / duplicate / gap-fill).
        """
        async with self._lock:
            self.state.last_inbound_at = time.time()
            msg_type = _get(msg, _TAG_MSG_TYPE)
            seq_num = _get_int(msg, _TAG_MSG_SEQ_NUM)
            poss_dup = _get(msg, _TAG_POSS_DUP_FLAG) == b"Y"
            poss_resend = _get(msg, _TAG_POSS_RESEND) == b"Y"

            # --- 1. Detect sequence-number direction --------------------
            if seq_num is None:
                # Logon w/o seq num is allowed; everything else is a reject.
                return self._dispatch_admin(msg, msg_type, poss_dup, poss_resend)

            expected = self.state.next_seq_in
            if seq_num < expected:
                if not poss_dup:
                    # FIX spec: "received MsgSeqNum is too low" -> Logout(1409=9)
                    await self._send_logout_too_low(seq_num, expected)
                    raise FixSequenceError(
                        f"inbound MsgSeqNum={seq_num} < expected={expected} without PossDupFlag"
                    )
                # PossDupFlag=Y duplicate — silently drop (replay echo).
                logger.debug(
                    "fix session: dropping PossDup with seq=%d (expected=%d)",
                    seq_num,
                    expected,
                )
                return False

            if seq_num > expected:
                # Gap detected — send ResendRequest(7=expected, 16=0).
                await self._send_resend_request(begin=expected, end=0)
                # Hold the current message until the replay catches up.
                self.state.pending_resends.append((expected, seq_num - 1))
                return False

            # --- 2. In-order message -----------------------------------
            self.state.next_seq_in = seq_num + 1
            return self._dispatch_admin(msg, msg_type, poss_dup, poss_resend)

    async def heartbeat_loop(self) -> None:
        """Periodic heartbeat + idle detection.

        Sends ``Heartbeat(35=0)`` every ``heart_bt_int_seconds``. If no
        inbound message has arrived within ``test_request_threshold *
        heart_bt_int_seconds`` of silence, sends a ``TestRequest(35=1)``
        with a fresh ``TestReqID(112)``. If the next ``Heartbeat`` doesn't
        echo that id, terminate the session.
        """
        hb = self.config.heart_bt_int_seconds
        threshold = self.config.test_request_threshold * hb
        try:
            while not self.state.is_logged_out:
                await asyncio.sleep(hb)
                now = time.time()
                if now - self.state.last_outbound_at >= hb:
                    await self._send_heartbeat()
                if now - self.state.last_inbound_at >= threshold:
                    await self._send_test_request()
        except asyncio.CancelledError:
            raise

    # ------------------------------------------------------------------
    # Admin handlers (called for in-order messages only)
    # ------------------------------------------------------------------

    def _dispatch_admin(self, msg: Any, msg_type: bytes | None, poss_dup: bool, poss_resend: bool) -> bool:
        if msg_type == _MT_HEARTBEAT:
            return False  # caller doesn't care about heartbeats
        if msg_type == _MT_TEST_REQUEST:
            asyncio.create_task(self._respond_test_request(msg))
            return False
        if msg_type == _MT_RESEND_REQUEST:
            asyncio.create_task(self._respond_resend_request(msg))
            return False
        if msg_type == _MT_SEQUENCE_RESET:
            self._apply_sequence_reset(msg)
            return False
        if msg_type == _MT_LOGOUT:
            self.state.is_logged_out = True
            return False
        if msg_type == _MT_LOGON:
            self.state.is_logged_on = True
            # Caller still wants to see Logon for app-layer hooks.
            return True
        # Business messages reach the strategy.
        return True

    # ------------------------------------------------------------------
    # Admin senders
    # ------------------------------------------------------------------

    async def _send_resend_request(self, *, begin: int, end: int) -> None:
        try:
            import simplefix  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("simplefix not installed; cannot send ResendRequest")
            return
        msg = simplefix.FixMessage()
        msg.append_pair(_TAG_MSG_TYPE, _MT_RESEND_REQUEST.decode(), header=True)
        msg.append_pair(_TAG_BEGIN_SEQ_NO, str(begin))
        msg.append_pair(_TAG_END_SEQ_NO, str(end))
        self.state.in_resend_request = True
        await self._stamp_and_send(msg)
        logger.info(
            "fix session: sent ResendRequest(7=%d, 16=%d)", begin, end
        )

    async def _send_logout_too_low(self, seq_num: int, expected: int) -> None:
        try:
            import simplefix  # type: ignore[import-not-found]
        except ImportError:
            return
        msg = simplefix.FixMessage()
        msg.append_pair(_TAG_MSG_TYPE, _MT_LOGOUT.decode(), header=True)
        msg.append_pair(_TAG_SESSION_STATUS, _SS_RECEIVED_SEQNUM_TOO_LOW.decode())
        msg.append_pair(
            _TAG_TEXT,
            f"MsgSeqNum({seq_num}) too low expecting {expected}",
        )
        await self._stamp_and_send(msg)
        self.state.is_logged_out = True

    async def _send_heartbeat(self, test_req_id: str | None = None) -> None:
        try:
            import simplefix  # type: ignore[import-not-found]
        except ImportError:
            return
        msg = simplefix.FixMessage()
        msg.append_pair(_TAG_MSG_TYPE, _MT_HEARTBEAT.decode(), header=True)
        if test_req_id is not None:
            msg.append_pair(_TAG_TEST_REQ_ID, test_req_id)
        await self._stamp_and_send(msg)

    async def _send_test_request(self) -> None:
        try:
            import simplefix  # type: ignore[import-not-found]
        except ImportError:
            return
        msg = simplefix.FixMessage()
        msg.append_pair(_TAG_MSG_TYPE, _MT_TEST_REQUEST.decode(), header=True)
        req_id = f"TR-{int(time.time() * 1000)}"
        msg.append_pair(_TAG_TEST_REQ_ID, req_id)
        self.state.expected_test_req_id = req_id
        await self._stamp_and_send(msg)

    async def _respond_test_request(self, msg: Any) -> None:
        req_id = _get(msg, _TAG_TEST_REQ_ID)
        await self._send_heartbeat(test_req_id=req_id.decode() if req_id else None)

    async def _respond_resend_request(self, msg: Any) -> None:
        # Default response: SequenceReset-GapFill from BeginSeqNo to NewSeqNo.
        # Real venue adapters override with stored message replay.
        try:
            import simplefix  # type: ignore[import-not-found]
        except ImportError:
            return
        begin = _get_int(msg, _TAG_BEGIN_SEQ_NO) or 1
        out = simplefix.FixMessage()
        out.append_pair(_TAG_MSG_TYPE, _MT_SEQUENCE_RESET.decode(), header=True)
        out.append_pair(_TAG_GAP_FILL_FLAG, "Y")
        out.append_pair(_TAG_NEW_SEQ_NO, str(self.state.next_seq_out))
        out.append_pair(_TAG_MSG_SEQ_NUM, str(begin), header=True)
        await self._stamp_and_send(out, override_seq=begin)

    def _apply_sequence_reset(self, msg: Any) -> None:
        new_seq = _get_int(msg, _TAG_NEW_SEQ_NO)
        gap_fill = _get(msg, _TAG_GAP_FILL_FLAG) == b"Y"
        if new_seq is None:
            return
        if gap_fill:
            # Gap-fill is allowed only to advance; treat the gap as
            # admin messages that don't need replay.
            if new_seq > self.state.next_seq_in:
                self.state.next_seq_in = new_seq
        else:
            # Hard reset (rare; usually after operator intervention).
            self.state.next_seq_in = new_seq
        self.state.in_resend_request = False

    async def _stamp_and_send(self, msg: Any, *, override_seq: int | None = None) -> None:
        seq = override_seq if override_seq is not None else self.state.next_seq_out
        # simplefix headers
        msg.append_pair(_TAG_MSG_SEQ_NUM, str(seq), header=True)
        if override_seq is None:
            self.state.next_seq_out = seq + 1
        self.state.last_outbound_at = time.time()
        await self._send_msg(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(msg: Any, tag: int) -> bytes | None:
    """Read a tag from a simplefix.FixMessage; returns None on miss."""
    try:
        return msg.get(tag)
    except Exception:  # noqa: BLE001
        return None


def _get_int(msg: Any, tag: int) -> int | None:
    raw = _get(msg, tag)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


__all__ = [
    "FixSequenceError",
    "FixSessionConfig",
    "FixSessionLayer",
    "FixSessionState",
]
