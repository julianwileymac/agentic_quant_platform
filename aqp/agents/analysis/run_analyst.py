"""Analysis agent: interpret a backtest / paper / live run end-to-end."""
from __future__ import annotations

from aqp.agents.spec import AgentSpec, GuardrailSpec, MemorySpec, ModelRef, RAGRef, ToolRef


SYSTEM = """You are a backtest run analyst. Input: a backtest_run row + key metrics
(sharpe, sortino, max_drawdown, total_return, ...). Output JSON:

{
  "headline": "...",
  "strengths": [...],
  "weaknesses": [...],
  "regime_attribution": "...",  // bull | bear | mean-reverting | trending | choppy
  "next_actions": [...],         // 1-5 follow-ups (e.g. param sweep, regime gate)
  "score": 0..10,
  "rationale": "..."
}
"""


def build_run_analyst_spec() -> AgentSpec:
    return AgentSpec(
        name="analysis.run",
        role="run_analyst",
        description="Interpret a single backtest / paper / live run.",
        system_prompt=SYSTEM,
        model=ModelRef(provider="ollama", model="", tier="deep", temperature=0.15),
        tools=[
            ToolRef(name="metrics"),
            ToolRef(name="rag_query"),
            ToolRef(name="optimize_proposal"),
            ToolRef(name="annotation"),
        ],
        memory=MemorySpec(kind="redis_hybrid", role="analysis.run", working_max=64),
        rag=[
            RAGRef(
                levels=["l0", "l1"],
                orders=["first"],
                corpora=["performance", "decisions"],
                per_level_k=5,
                final_k=10,
            ),
        ],
        guardrails=GuardrailSpec(require_rationale=True, cost_budget_usd=0.5),
        max_cost_usd=0.5,
        max_calls=10,
        annotations=["analysis", "run"],
    )
