"""Bot lifecycle state machine.

Ten canonical states (blueprint §A.3) — the operator status conditions
mirror these names, so a ``status.phase=Draining`` on a Bot CR maps
1:1 onto :class:`BotState.DRAINING`.

The FSM is **finalizer-protected**: the operator's ``quantbot.io/graceful-drain``
finalizer drives the ``Running → Draining → Stopped`` transition via
SIGTERM + ``terminationGracePeriodSeconds`` (30s for HFT, 300s for
everything else).

State diagram::

                    Provisioning
                        |
                    Initializing
                        |
                    WarmingUp
                        |
                       Running <----+
                       / | \\         |
                      /  |  \\        | resume
                     /   |   \\       |
                Paused -----'         |
                    \\                 |
                     \\----> Draining -+
                                |
                                v
                             Stopped
                              | reconcile (after restart)
                              v
                          Reconciling --> Running

    Any state can transition to Failed (terminal error) or Killed
    (emergency, no flatten).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class BotState(StrEnum):
    """Lifecycle states a bot passes through.

    The operator's ``status.phase`` field on a ``Bot`` CR is a string
    representation of one of these values.
    """

    PROVISIONING = "Provisioning"
    INITIALIZING = "Initializing"
    WARMING_UP = "WarmingUp"
    RUNNING = "Running"
    PAUSED = "Paused"
    DRAINING = "Draining"
    STOPPED = "Stopped"
    KILLED = "Killed"
    RECONCILING = "Reconciling"
    FAILED = "Failed"


class LifecycleError(RuntimeError):
    """Raised when an illegal state transition is attempted."""


_TERMINAL: frozenset[BotState] = frozenset(
    {BotState.STOPPED, BotState.KILLED, BotState.FAILED}
)


# Valid forward transitions.  Killed/Failed are always reachable from any
# non-terminal state; that fan-in is handled in :meth:`LifecycleFSM.kill`
# and :meth:`LifecycleFSM.fail` rather than enumerated here.
_VALID_TRANSITIONS: dict[BotState, frozenset[BotState]] = {
    BotState.PROVISIONING: frozenset(
        {BotState.INITIALIZING, BotState.FAILED, BotState.KILLED}
    ),
    BotState.INITIALIZING: frozenset(
        {BotState.WARMING_UP, BotState.FAILED, BotState.KILLED}
    ),
    BotState.WARMING_UP: frozenset(
        {BotState.RUNNING, BotState.FAILED, BotState.KILLED}
    ),
    BotState.RUNNING: frozenset(
        {BotState.PAUSED, BotState.DRAINING, BotState.FAILED, BotState.KILLED}
    ),
    BotState.PAUSED: frozenset(
        {BotState.RUNNING, BotState.DRAINING, BotState.FAILED, BotState.KILLED}
    ),
    BotState.DRAINING: frozenset(
        {BotState.STOPPED, BotState.FAILED, BotState.KILLED}
    ),
    BotState.STOPPED: frozenset({BotState.RECONCILING, BotState.KILLED}),
    BotState.RECONCILING: frozenset(
        {BotState.RUNNING, BotState.FAILED, BotState.KILLED}
    ),
    BotState.KILLED: frozenset(),
    BotState.FAILED: frozenset({BotState.RECONCILING, BotState.KILLED}),
}


@dataclass(slots=True, frozen=True)
class TransitionEvent:
    """One state transition.  Emitted to lifecycle subscribers."""

    from_state: BotState
    to_state: BotState
    reason: str
    at_utc: datetime
    extras: dict[str, Any] = field(default_factory=dict)


LifecycleHook = Callable[[TransitionEvent], None]


class LifecycleFSM:
    """Bot lifecycle state machine.

    The FSM keeps an in-memory history of every transition so the operator
    can populate the CR's ``status.conditions`` array directly from the
    most recent N transitions. The runtime calls :meth:`subscribe` to
    receive transition events as they happen — used for telemetry, audit,
    and the kill-switch fan-out.
    """

    def __init__(self, initial: BotState = BotState.PROVISIONING) -> None:
        self._state: BotState = initial
        self._history: list[TransitionEvent] = []
        self._hooks: list[LifecycleHook] = []

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def state(self) -> BotState:
        return self._state

    @property
    def history(self) -> tuple[TransitionEvent, ...]:
        return tuple(self._history)

    def is_terminal(self) -> bool:
        return self._state in _TERMINAL

    def is_running(self) -> bool:
        return self._state == BotState.RUNNING

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, hook: LifecycleHook) -> None:
        """Register ``hook`` to receive every transition event."""
        self._hooks.append(hook)

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def transition(
        self,
        target: BotState,
        *,
        reason: str = "",
        extras: dict[str, Any] | None = None,
    ) -> TransitionEvent:
        """Move to ``target``.  Raises :class:`LifecycleError` if illegal."""
        valid = _VALID_TRANSITIONS.get(self._state, frozenset())
        if target not in valid and target not in {BotState.KILLED, BotState.FAILED}:
            raise LifecycleError(
                f"Illegal transition {self._state.value} -> {target.value}; "
                f"valid: {sorted(s.value for s in valid)}"
            )
        evt = TransitionEvent(
            from_state=self._state,
            to_state=target,
            reason=reason,
            at_utc=datetime.now(timezone.utc),
            extras=extras or {},
        )
        self._state = target
        self._history.append(evt)
        for hook in self._hooks:
            try:
                hook(evt)
            except Exception:  # noqa: BLE001
                logger.debug("lifecycle hook raised; ignoring", exc_info=True)
        return evt

    def kill(self, *, reason: str = "manual") -> TransitionEvent:
        """Emergency kill — bypasses drain. Always legal from non-terminal states."""
        if self._state == BotState.KILLED:
            return self._history[-1] if self._history else TransitionEvent(
                from_state=BotState.KILLED,
                to_state=BotState.KILLED,
                reason="already killed",
                at_utc=datetime.now(timezone.utc),
            )
        return self.transition(BotState.KILLED, reason=reason)

    def fail(self, *, reason: str, extras: dict[str, Any] | None = None) -> TransitionEvent:
        """Mark the bot as failed.  Always legal."""
        return self.transition(BotState.FAILED, reason=reason, extras=extras)


__all__ = [
    "BotState",
    "LifecycleError",
    "LifecycleFSM",
    "LifecycleHook",
    "TransitionEvent",
]
