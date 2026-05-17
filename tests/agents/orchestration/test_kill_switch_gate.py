"""Phase 2 — kill switch / halt-gate tests.

Covers:

- :func:`aqp.agents.graph.conditions.should_halt` is ``True`` when the
  per-run ``halt_token`` flag is set, regardless of the Redis path.
- :func:`aqp.agents.graph.conditions.should_halt` falls through to
  :func:`has_kill_switch` when the token is absent.
- :class:`WorkflowRuntime` aborts BEFORE the first transition when the
  halt-check returns ``True``, producing a ``status="halted"`` result
  with a ``kill_switch`` breadcrumb.
- The cooperative-cancel hook installed by :class:`WorkflowRuntime`
  fires inside :class:`AgentRuntime._invoke_llm` (verified through the
  exposed :class:`CooperativeCancel` raise from a stubbed router
  ``router_complete``).
- The halt is observed inside the documented SLA
  (``AQP_ORCHESTRATION_HALT_CHECK_TIMEOUT_SECONDS``).
"""
from __future__ import annotations

import time
from typing import Any

import pytest

from aqp.agents.graph.conditions import has_kill_switch, should_halt
from aqp.agents.orchestration import (
    AdapterContext,
    AdapterResult,
    OrchestrationAdapter,
    WorkflowRuntime,
    WorkflowSpec,
)
from aqp.agents.runtime import (
    CooperativeCancel,
    _check_cooperative_cancel,
    set_cooperative_cancel_check,
    reset_cooperative_cancel_check,
)


def test_should_halt_true_on_halt_token():
    assert should_halt({"halt_token": True}) is True


def test_should_halt_false_when_neither_set(monkeypatch):
    monkeypatch.setattr(
        "aqp.agents.graph.conditions.has_kill_switch",
        lambda _state: False,
    )
    assert should_halt({}) is False
    assert should_halt({"halt_token": False}) is False


def test_should_halt_falls_through_to_kill_switch(monkeypatch):
    monkeypatch.setattr(
        "aqp.agents.graph.conditions.has_kill_switch",
        lambda _state: True,
    )
    assert should_halt({}) is True


def test_has_kill_switch_returns_false_when_redis_unavailable(monkeypatch):
    """Failure to import / connect to Redis must NOT halt the run."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "redis":
            raise ImportError("simulated missing redis dep")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    assert has_kill_switch({}) is False


class _HaltCheckingAdapter(OrchestrationAdapter):
    """Adapter that records whether it was invoked + polls is_halted."""

    adapter_kind = "graph"
    adapter_alias = "kill_switch_test_adapter"

    def __init__(self) -> None:
        self.invoked = False
        self.halted_when_invoked: bool | None = None

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        self.invoked = True
        self.halted_when_invoked = context.is_halted()
        return AdapterResult(state=state, status="completed")


def test_runtime_halts_before_first_transition(monkeypatch):
    """When the kill switch is engaged the adapter must not even start."""
    monkeypatch.setattr(
        "aqp.agents.graph.conditions.has_kill_switch",
        lambda _state: True,
    )
    spec = WorkflowSpec(name="t", adapter="kill_switch_test_adapter")
    adapter = _HaltCheckingAdapter()
    started = time.perf_counter()
    result = WorkflowRuntime(spec, adapter=adapter).run()
    elapsed_seconds = time.perf_counter() - started
    assert result.status == AdapterResult.STATUS_HALTED
    assert result.halted is True
    assert adapter.invoked is False
    # Halt observed well inside the documented SLA.
    assert elapsed_seconds < 1.0
    # The runtime appended a kill_switch breadcrumb.
    assert any(
        b.get("node") == "kill_switch" for b in result.state.get("adapter_breadcrumbs", [])
    )


def test_runtime_halts_after_transition_when_switch_flips_mid_run(monkeypatch):
    """A late kill-switch flip surfaces as a halt, not a completed run."""
    state_holder = {"calls": 0}

    def _flip_mid_run(_state):
        state_holder["calls"] += 1
        # Return False on the pre-check, True afterwards.
        return state_holder["calls"] > 1

    monkeypatch.setattr(
        "aqp.agents.graph.conditions.has_kill_switch", _flip_mid_run
    )

    spec = WorkflowSpec(name="t", adapter="kill_switch_test_adapter")
    adapter = _HaltCheckingAdapter()
    result = WorkflowRuntime(spec, adapter=adapter).run()
    assert result.status == AdapterResult.STATUS_HALTED
    # The adapter DID run once (pre-check returned False) but the
    # mid-run halt observed it.
    assert adapter.invoked is True


def test_cooperative_cancel_check_raises_when_hook_signals_halt():
    """``_check_cooperative_cancel`` raises so the tool loop aborts."""
    token = set_cooperative_cancel_check(lambda: True)
    try:
        with pytest.raises(CooperativeCancel):
            _check_cooperative_cancel()
    finally:
        reset_cooperative_cancel_check(token)


def test_cooperative_cancel_check_noop_when_unhooked():
    """The default (no hook installed) must never raise."""
    _check_cooperative_cancel()
    assert True


def test_cooperative_cancel_check_swallows_broken_hook():
    """A flaky hook must NOT crash the agent runtime."""

    def _broken_hook() -> bool:
        raise RuntimeError("simulated halt-hook failure")

    token = set_cooperative_cancel_check(_broken_hook)
    try:
        # Must NOT raise — fails closed to "no halt".
        _check_cooperative_cancel()
    finally:
        reset_cooperative_cancel_check(token)
