"""ResearchBot chat dispatches through AgentRuntime (mocked LLM)."""
from __future__ import annotations

from typing import Any

import pytest

from aqp.bots.research_bot import ResearchBot
from aqp.bots.spec import BotAgentRef, BotSpec, RAGRef


def _research_spec(**overrides: Any) -> BotSpec:
    base = dict(
        name="Research Bot",
        kind="research",
        agents=[
            BotAgentRef(spec_name="research.equity", role="equity_analyst"),
            BotAgentRef(spec_name="research.quant_vbtpro", role="quant_analyst"),
        ],
        rag=[
            RAGRef(levels=["l3"], orders=["third"], corpora=["strategies"], per_level_k=4),
        ],
    )
    base.update(overrides)
    return BotSpec(**base)


class _FakeAgentSpec:
    def __init__(self, name: str) -> None:
        self.name = name
        self.role = "research"


class _FakeAgentRunResult:
    def __init__(self, name: str, prompt: str) -> None:
        self.run_id = f"agent-run-{name}"
        self.spec_name = name
        self.status = "completed"
        self.output = {"text": f"reply from {name}: {prompt[:40]}", "rationale": "auto"}
        self.cost_usd = 0.0
        self.n_calls = 1
        self.n_tool_calls = 0
        self.n_rag_hits = 0
        self.steps = []
        self.error = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec_name": self.spec_name,
            "status": self.status,
            "output": self.output,
            "cost_usd": self.cost_usd,
            "n_calls": self.n_calls,
            "n_tool_calls": self.n_tool_calls,
            "n_rag_hits": self.n_rag_hits,
            "steps": [],
            "error": None,
        }


class _FakeAgentRuntime:
    instances: list["_FakeAgentRuntime"] = []

    def __init__(self, spec: _FakeAgentSpec, *, session_id: str | None = None) -> None:
        self.spec = spec
        self.session_id = session_id
        self.received_inputs: dict[str, Any] = {}
        _FakeAgentRuntime.instances.append(self)

    def run(self, inputs: dict[str, Any]) -> _FakeAgentRunResult:
        self.received_inputs = dict(inputs)
        return _FakeAgentRunResult(self.spec.name, inputs.get("prompt", ""))


@pytest.fixture(autouse=True)
def _patch_runtime(monkeypatch):
    """Replace AgentRuntime + get_agent_spec for hermetic chat tests."""
    _FakeAgentRuntime.instances.clear()
    monkeypatch.setattr(
        "aqp.agents.runtime.AgentRuntime", _FakeAgentRuntime, raising=True
    )
    monkeypatch.setattr(
        "aqp.agents.registry.get_agent_spec",
        lambda name: _FakeAgentSpec(name),
        raising=True,
    )
    yield
    _FakeAgentRuntime.instances.clear()


def test_chat_calls_every_agent_and_aggregates_replies() -> None:
    bot = ResearchBot(spec=_research_spec())
    result = bot.chat("Tell me about AAPL")

    assert result["bot_kind"] == "research"
    assert result["prompt"] == "Tell me about AAPL"
    assert set(result["replies"].keys()) == {"research.equity", "research.quant_vbtpro"}
    for name, payload in result["replies"].items():
        assert payload["status"] == "completed"
        assert payload["output"]["text"].startswith(f"reply from {name}")


def test_chat_filters_by_role() -> None:
    bot = ResearchBot(spec=_research_spec())
    result = bot.chat("Quant question", agent_role="quant_analyst")
    assert list(result["replies"].keys()) == ["research.quant_vbtpro"]


def test_chat_skips_disabled_agents() -> None:
    spec = _research_spec(
        agents=[
            BotAgentRef(spec_name="research.equity", role="equity_analyst", enabled=True),
            BotAgentRef(spec_name="research.disabled", role="off", enabled=False),
        ],
    )
    bot = ResearchBot(spec=spec)
    result = bot.chat("Hello")
    assert "research.disabled" not in result["replies"]
    assert "research.equity" in result["replies"]


def test_chat_session_id_propagates_to_agent_runtime() -> None:
    bot = ResearchBot(spec=_research_spec())
    bot.chat("Hi", session_id="sess-123")
    assert all(rt.session_id == "sess-123" for rt in _FakeAgentRuntime.instances)


def test_chat_inputs_template_merges_with_caller_inputs() -> None:
    spec = _research_spec(
        agents=[
            BotAgentRef(
                spec_name="research.equity",
                role="equity_analyst",
                inputs_template={"style": "long-form", "language": "en"},
            )
        ],
    )
    bot = ResearchBot(spec=spec)
    bot.chat("Question?", inputs={"language": "fr", "extra": True})
    rt = _FakeAgentRuntime.instances[-1]
    assert rt.received_inputs["style"] == "long-form"  # from template
    assert rt.received_inputs["language"] == "fr"  # caller override wins
    assert rt.received_inputs["extra"] is True
    assert rt.received_inputs["prompt"] == "Question?"


def test_chat_summary_renders_text_replies() -> None:
    bot = ResearchBot(spec=_research_spec())
    result = bot.chat("Tell me about MSFT")
    assert "research.equity" in result["summary"]
    assert "reply from research.equity" in result["summary"]


def test_chat_unknown_spec_is_skipped(monkeypatch) -> None:
    """Unknown specs in the registry don't crash the bot — they're skipped."""
    def _missing(name: str):
        if name == "research.equity":
            return _FakeAgentSpec(name)
        raise KeyError(name)

    monkeypatch.setattr("aqp.agents.registry.get_agent_spec", _missing, raising=True)

    spec = _research_spec(
        agents=[
            BotAgentRef(spec_name="research.equity", role="equity_analyst"),
            BotAgentRef(spec_name="research.does-not-exist", role="ghost"),
        ],
    )
    bot = ResearchBot(spec=spec)
    result = bot.chat("Hello")
    assert "research.equity" in result["replies"]
    assert "research.does-not-exist" not in result["replies"]


def test_research_bot_repr_does_not_crash() -> None:
    bot = ResearchBot(spec=_research_spec())
    assert "ResearchBot" in repr(bot)
