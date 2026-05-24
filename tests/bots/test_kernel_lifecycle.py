"""Phase 2: BotKernel + LifecycleFSM."""
from __future__ import annotations

import pytest

from aqp_bots.core.lifecycle import BotState, LifecycleError, LifecycleFSM


def test_fsm_initial_state() -> None:
    fsm = LifecycleFSM()
    assert fsm.state == BotState.PROVISIONING
    assert not fsm.is_running()
    assert not fsm.is_terminal()


def test_fsm_happy_path() -> None:
    fsm = LifecycleFSM()
    fsm.transition(BotState.INITIALIZING, reason="bring-up")
    fsm.transition(BotState.WARMING_UP, reason="warmup")
    fsm.transition(BotState.RUNNING, reason="ready")
    assert fsm.is_running()
    fsm.transition(BotState.DRAINING, reason="shutdown")
    fsm.transition(BotState.STOPPED, reason="drain complete")
    assert fsm.is_terminal()


def test_fsm_illegal_transition_raises() -> None:
    fsm = LifecycleFSM()
    with pytest.raises(LifecycleError):
        fsm.transition(BotState.RUNNING)


def test_fsm_kill_is_always_legal() -> None:
    fsm = LifecycleFSM()
    fsm.transition(BotState.INITIALIZING)
    fsm.kill(reason="emergency")
    assert fsm.state == BotState.KILLED
    assert fsm.is_terminal()


def test_fsm_fail_is_always_legal() -> None:
    fsm = LifecycleFSM()
    fsm.transition(BotState.INITIALIZING)
    fsm.fail(reason="adapter exception")
    assert fsm.state == BotState.FAILED


def test_fsm_records_history() -> None:
    fsm = LifecycleFSM()
    fsm.transition(BotState.INITIALIZING, reason="step 1")
    fsm.transition(BotState.WARMING_UP, reason="step 2")
    history = fsm.history
    assert len(history) == 2
    assert history[0].from_state == BotState.PROVISIONING
    assert history[1].to_state == BotState.WARMING_UP


def test_fsm_hooks_fire() -> None:
    events: list[str] = []
    fsm = LifecycleFSM()
    fsm.subscribe(lambda evt: events.append(f"{evt.from_state.value}->{evt.to_state.value}"))
    fsm.transition(BotState.INITIALIZING)
    fsm.transition(BotState.WARMING_UP)
    assert events == ["Provisioning->Initializing", "Initializing->WarmingUp"]
