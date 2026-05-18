"""Regression test for defect 6: quant wrappers misuse :class:`AgentRunResult`.

Before the fix, :class:`aqp.agents.quant.alpha_researcher.AlphaResearcher`
and :class:`aqp.agents.quant.strategy_executor.StrategyExecutor` consumed
``runtime.run(inputs)`` with ``result.get("output") if isinstance(result, dict) else None``
— but :meth:`AgentRuntime.run` always returns an
:class:`AgentRunResult` dataclass, so ``isinstance(result, dict)`` was
always False and the wrappers silently returned ``{}`` every call.
"""
from __future__ import annotations

from typing import Any

import pytest

from aqp.agents.runtime import AgentRunResult


@pytest.fixture
def fake_agent_run_result() -> AgentRunResult:
    return AgentRunResult(
        run_id="run-1",
        spec_name="quant.alpha",
        status="completed",
        output={
            "name": "test_factor",
            "formula": "ts_zscore(close, 20)",
            "rationale": "demo",
            "constraints": {"max_position": 0.05, "cost_bps": 1.0},
        },
        cost_usd=0.0,
        n_calls=1,
        n_tool_calls=0,
        n_rag_hits=0,
    )


def test_alpha_researcher_consumes_agent_run_result(monkeypatch, fake_agent_run_result):
    """``AlphaResearcher.propose`` reads ``result.output`` directly.

    The wrapper imports ``AgentRuntime`` lazily inside ``propose`` so
    we patch the *source* module path (``aqp.agents.runtime``) to make
    sure the local ``from aqp.agents.runtime import AgentRuntime``
    picks up the stub.
    """
    from aqp.agents.quant import alpha_researcher as ar_mod

    class _StubRuntime:
        def __init__(self, *_: Any, **__: Any) -> None:
            return None

        def run(self, *, inputs: dict[str, Any]) -> AgentRunResult:
            return fake_agent_run_result

    class _StubSpec:
        name = "research.alpha_proposer"

    monkeypatch.setattr("aqp.agents.runtime.AgentRuntime", _StubRuntime)
    monkeypatch.setattr(
        "aqp.agents.registry.get_agent_spec",
        lambda *_: _StubSpec(),
    )

    researcher = ar_mod.AlphaResearcher(
        agent_spec_name="research.alpha_proposer"
    )
    proposal = researcher.propose({"intent": "test"})

    # Before the fix this would silently degrade to the heuristic
    # default regardless of what the agent emitted. After the fix the
    # raw payload reaches ``_coerce_proposal`` and the formula round-trips.
    assert isinstance(proposal, dict)
    assert proposal.get("formula") == "ts_zscore(close, 20)"
    assert proposal.get("name") == "test_factor"


def test_strategy_executor_consumes_agent_run_result(monkeypatch, fake_agent_run_result):
    """``StrategyExecutor.decide_and_run`` reads ``result.output`` directly."""
    from aqp.agents.quant import strategy_executor as se_mod

    fake_agent_run_result.output = {
        "intent": "paper",
        "experiment_slug": "demo.exp",
        "rationale": "ship it",
        "go": False,
        "window": {},
    }

    class _StubRuntime:
        def __init__(self, *_: Any, **__: Any) -> None:
            return None

        def run(self, *, inputs: dict[str, Any]) -> AgentRunResult:
            return fake_agent_run_result

    class _StubSpec:
        name = "strategy.executor"

    monkeypatch.setattr("aqp.agents.runtime.AgentRuntime", _StubRuntime)
    monkeypatch.setattr(
        "aqp.agents.registry.get_agent_spec",
        lambda *_: _StubSpec(),
    )

    executor = se_mod.StrategyExecutor(
        agent_spec_name="strategy.executor", require_kill_switch_clear=False
    )
    result = executor.decide_and_run({"intent": "paper"})
    assert getattr(result, "intent", None) == "paper"
    assert getattr(result, "experiment_slug", None) == "demo.exp"
    assert getattr(result, "go", None) is False


def test_alpha_researcher_handles_error_status(monkeypatch):
    """An ``error`` status yields an empty output without crashing."""
    from aqp.agents.quant import alpha_researcher as ar_mod

    err_result = AgentRunResult(
        run_id="run-err",
        spec_name="x",
        status="error",
        output={},
        cost_usd=0.0,
        n_calls=0,
        n_tool_calls=0,
        n_rag_hits=0,
        error="boom",
    )

    class _StubRuntime:
        def __init__(self, *_: Any, **__: Any) -> None:
            return None

        def run(self, *, inputs: dict[str, Any]) -> AgentRunResult:
            return err_result

    class _StubSpec:
        name = "research.alpha_proposer"

    monkeypatch.setattr("aqp.agents.runtime.AgentRuntime", _StubRuntime)
    monkeypatch.setattr(
        "aqp.agents.registry.get_agent_spec",
        lambda *_: _StubSpec(),
    )

    researcher = ar_mod.AlphaResearcher(
        agent_spec_name="research.alpha_proposer"
    )
    proposal = researcher.propose({"intent": "test"})
    # When the agent errored, the wrapper passes an empty payload
    # through ``_coerce_proposal`` — the existing implementation
    # returns the dict unchanged, so an error becomes an empty dict
    # the caller can detect (rather than masking the error with a
    # synthetic proposal that would silently get evaluated).
    assert isinstance(proposal, dict)
    assert proposal == {}
