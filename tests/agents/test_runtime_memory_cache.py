"""Regression test for defect 1: memory cache must not leak into tool list.

Before the fix, :class:`aqp.agents.runtime.AgentRuntime` stored its
:class:`RedisHybridMemory` instance under ``self._tool_cache["__memory__"]``
while ``_resolve_tools()`` returned ``list(self._tool_cache.values())``.
A memory-enabled spec with multiple tools therefore ended up surfacing
a memory object inside the OpenAI tool catalog when ``_invoke_llm``
iterated the resolved tools.

The fix moves memory into a dedicated ``_memory_instance`` /
``_memory_resolved`` slot pair (already declared on the runtime) so
``_resolve_tools()`` only ever returns concrete tool instances.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from aqp.agents.runtime import AgentRuntime
from aqp.agents.spec import AgentSpec, MemorySpec, ModelRef, ToolRef


class _StubTool:
    """Minimal tool stand-in matching crewai.tools.BaseTool surface."""

    name = "stub_tool"
    description = ""
    args_schema = None

    def __init__(self, **_: Any) -> None:  # noqa: D401
        return None

    def _run(self, **_: Any) -> str:
        return "ok"


class _OtherStubTool(_StubTool):
    name = "other_stub"


def _make_spec() -> AgentSpec:
    return AgentSpec(
        name="defect1.memory_isolation",
        role="tester",
        system_prompt="t",
        model=ModelRef(provider="ollama", model="test", tier="quick"),
        tools=[ToolRef(name="stub_tool"), ToolRef(name="other_stub")],
        memory=MemorySpec(kind="bm25", role="defect1.memory_isolation"),
    )


def test_resolve_tools_excludes_memory_instance(monkeypatch):
    """``_resolve_tools()`` returns only the spec.tools, never memory."""
    spec = _make_spec()
    runtime = AgentRuntime(spec)

    monkeypatch.setattr(
        "aqp.agents.tools.TOOL_REGISTRY",
        {"stub_tool": _StubTool, "other_stub": _OtherStubTool},
        raising=False,
    )

    # Force memory to resolve to a sentinel BEFORE tool resolution so
    # the legacy bug (memory leaking into _tool_cache) would surface.
    fake_memory = SimpleNamespace(working_push=lambda *_: None, recall=lambda *_, **__: [])
    monkeypatch.setattr(runtime, "_memory", lambda: fake_memory)

    tools = runtime._resolve_tools()

    assert len(tools) == 2, f"expected 2 tools, got {len(tools)}: {tools!r}"
    assert all(isinstance(t, _StubTool) for t in tools), tools
    # And memory must never enter the cache under the legacy "__memory__" key.
    assert "__memory__" not in runtime._tool_cache


def test_memory_resolved_into_dedicated_slot(monkeypatch):
    """``_memory()`` populates ``_memory_instance`` / ``_memory_resolved``."""
    spec = _make_spec()
    runtime = AgentRuntime(spec)

    sentinel = object()

    class _FakeBM25:
        def __init__(self, *a: Any, **kw: Any) -> None:
            return None

    monkeypatch.setattr("aqp.llm.memory.BM25Memory", _FakeBM25, raising=False)

    mem = runtime._memory()
    assert mem is not None
    assert runtime._memory_resolved is True
    assert runtime._memory_instance is mem
    # Idempotent — second call returns the cached instance.
    assert runtime._memory() is mem
    # And tool cache is still pristine.
    assert "__memory__" not in runtime._tool_cache


def test_disabled_memory_returns_none_without_caching(monkeypatch):
    spec = AgentSpec(
        name="defect1.no_memory",
        role="tester",
        memory=MemorySpec(kind="none"),
        tools=[ToolRef(name="stub_tool")],
    )
    runtime = AgentRuntime(spec)
    monkeypatch.setattr(
        "aqp.agents.tools.TOOL_REGISTRY",
        {"stub_tool": _StubTool},
        raising=False,
    )
    assert runtime._memory() is None
    tools = runtime._resolve_tools()
    assert len(tools) == 1
    assert "__memory__" not in runtime._tool_cache
