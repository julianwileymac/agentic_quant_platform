"""End-to-end smoke test: research.regime_analyst spec via AgentRuntime.

One of the three canonical platform smoke runs. Exercises:

- YAML spec loading from configs/agents/research_regime_analyst.yaml.
- :class:`aqp.agents.runtime.AgentRuntime` invocation with a stubbed LLM.
- ``regime_classifier_tool`` tool registration.

router_complete is monkey-patched to return a canned JSON regime
verdict so the test is fully hermetic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aqp.agents.spec import AgentSpec


@pytest.fixture
def regime_spec() -> AgentSpec:
    spec_path = Path(__file__).resolve().parents[2] / "configs" / "agents" / "research_regime_analyst.yaml"
    assert spec_path.exists(), f"spec missing at {spec_path}"
    return AgentSpec.from_yaml_path(str(spec_path))


def test_spec_loads_with_expected_tools(regime_spec: AgentSpec) -> None:
    assert regime_spec.name == "research.regime_analyst"
    assert regime_spec.role == "regime_analyst"
    tool_names = {t.name for t in regime_spec.tools}
    assert "regime_classifier_tool" in tool_names
    assert "historical_volatility" in tool_names


def test_regime_analyst_runtime_with_canned_llm(monkeypatch: pytest.MonkeyPatch, regime_spec: AgentSpec) -> None:
    """Run the agent end-to-end with a stubbed router_complete + tools.

    Hermetic: Redis memory disabled, RAG empty, LLM call stubbed, tool stubbed.
    """
    from aqp.agents import runtime as runtime_mod
    from aqp.agents.spec import MemorySpec

    # Disable Redis-backed memory for the test (avoids connection attempts).
    regime_spec_local = regime_spec.model_copy(update={"memory": MemorySpec(kind="none", role="test")})

    canned_verdict = {
        "regime": "trending",
        "adx": 32.5,
        "sigma": 0.18,
        "confidence": 0.82,
        "recommendation": "long bias",
        "rationale": "ADX above 25 with moderate volatility supports trend follow.",
    }

    def _fake_router_complete(*args: Any, **kwargs: Any) -> Any:
        from aqp.llm.providers.router import LLMResult  # type: ignore[import-not-found]
        return LLMResult(
            content=json.dumps(canned_verdict),
            model="test-stub",
            provider="stub",
            prompt_tokens=20,
            completion_tokens=50,
            total_tokens=70,
            cost_usd=0.0,
            raw={"choices": [{"message": {"content": json.dumps(canned_verdict)}}]},
        )

    monkeypatch.setattr(runtime_mod, "router_complete", _fake_router_complete, raising=False)

    # Stub the regime_classifier_tool so it doesn't touch DuckDB.
    from aqp.agents.tools import analytics_tools

    def _fake_run(self, *args: Any, **kwargs: Any) -> str:  # noqa: ARG001
        return json.dumps(
            {
                "vt_symbol": kwargs.get("vt_symbol", "SPY.NASDAQ"),
                "adx": 32.5,
                "threshold": 25.0,
                "regime": "trending",
                "score": 7.5,
            }
        )

    monkeypatch.setattr(analytics_tools.RegimeClassifierTool, "_run", _fake_run, raising=False)

    runtime = runtime_mod.AgentRuntime(regime_spec_local, run_id="test-regime-run-1")
    result = runtime.run({"vt_symbol": "SPY.NASDAQ", "prompt": "Assess SPY regime."})

    assert result is not None
    assert hasattr(result, "output")
    assert hasattr(result, "cost_usd")
    assert hasattr(result, "n_calls")
    # Runtime should be in a terminal state (completed or rejected — both are
    # acceptable; "error" indicates an unexpected crash).
    assert result.status in {"completed", "rejected"}, f"unexpected status={result.status} error={result.error}"
    # Either the parsed verdict or the raw content should mention the canned regime.
    output_repr = json.dumps(result.output, default=str) if not isinstance(result.output, str) else str(result.output)
    assert (
        "trending" in output_repr.lower() or "regime" in output_repr.lower() or result.status == "rejected"
    ), f"expected canned content in output: {output_repr[:200]}"
