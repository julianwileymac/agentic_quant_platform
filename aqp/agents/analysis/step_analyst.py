"""Analysis agent: interpret a single agent step's tool calls + outputs."""
from __future__ import annotations

from aqp.agents.spec import AgentSpec, GuardrailSpec, MemorySpec, ModelRef, RAGRef, ToolRef


SYSTEM = """You are an agent step-analyser. Inputs:
- step: {kind, name, inputs, output, cost_usd, duration_ms, error?}
- run_context: brief context about the parent run.

Produce JSON: {
  "verdict": "useful" | "redundant" | "harmful" | "noise",
  "score": 0..10,
  "issues": [...],
  "improvements": [...],
  "rationale": "..."
}
"""


def build_step_analyst_spec() -> AgentSpec:
    return AgentSpec(
        name="analysis.step",
        role="step_analyst",
        description="Interpret a single agent step.",
        system_prompt=SYSTEM,
        model=ModelRef(provider="ollama", model="", tier="quick", temperature=0.1),
        tools=[ToolRef(name="annotation")],
        memory=MemorySpec(kind="bm25", role="analysis.step"),
        rag=[],
        guardrails=GuardrailSpec(require_rationale=True, cost_budget_usd=0.1),
        max_cost_usd=0.1,
        max_calls=2,
        annotations=["analysis", "step"],
    )
