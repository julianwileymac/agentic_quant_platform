"""AgentDispatcher tests — TTL/LRU caching with stubbed runtime."""
from __future__ import annotations

import time

import pytest

from aqp.strategies.agentic.agent_dispatcher import AgentDispatcher, get_default_dispatcher


def test_dispatcher_caches_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []

    class _StubRuntime:
        def __init__(self, spec_name: str) -> None:
            self.spec_name = spec_name

        def run(self, inputs):
            calls.append((self.spec_name, dict(inputs)))
            return {"output": {"action": "BUY", "confidence": 0.9}}

    def fake_runtime_for(name: str) -> _StubRuntime:
        return _StubRuntime(name)

    import aqp.agents.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "runtime_for", fake_runtime_for)

    dispatcher = AgentDispatcher(ttl_seconds=10.0)
    a = dispatcher.consult("trader.signal_emitter", {"vt_symbol": "AAPL.NASDAQ"})
    b = dispatcher.consult("trader.signal_emitter", {"vt_symbol": "AAPL.NASDAQ"})
    c = dispatcher.consult("trader.signal_emitter", {"vt_symbol": "MSFT.NASDAQ"})
    assert a == b
    assert len(calls) == 2  # cached for AAPL the second time, MSFT triggers a new call
    assert dispatcher.stats["cache_hits"] >= 1
    assert dispatcher.stats["runtime_calls"] == 2


def test_dispatcher_ttl_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    class _StubRuntime:
        def run(self, inputs):
            calls["n"] += 1
            return {"output": {"action": "BUY"}}

    monkeypatch.setattr("aqp.agents.runtime.runtime_for", lambda name: _StubRuntime())

    dispatcher = AgentDispatcher(ttl_seconds=0.01)
    dispatcher.consult("x", {"a": 1})
    time.sleep(0.05)
    dispatcher.consult("x", {"a": 1})
    assert calls["n"] == 2


def test_dispatcher_returns_none_when_runtime_disabled() -> None:
    dispatcher = AgentDispatcher(use_runtime=False)
    assert dispatcher.consult("any.spec", {"a": 1}) is None


def test_dispatcher_returns_none_on_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomRuntime:
        def run(self, inputs):
            raise RuntimeError("simulated failure")

    monkeypatch.setattr("aqp.agents.runtime.runtime_for", lambda name: _BoomRuntime())

    dispatcher = AgentDispatcher()
    result = dispatcher.consult("x", {"a": 1})
    assert result is None
    assert dispatcher.stats["errors"] == 1


def test_default_dispatcher_singleton() -> None:
    a = get_default_dispatcher()
    b = get_default_dispatcher()
    assert a is b
