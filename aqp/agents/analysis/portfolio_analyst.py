"""Analysis agent: interpret portfolio aggregate performance + risk."""
from __future__ import annotations

from aqp.agents.spec import AgentSpec, GuardrailSpec, MemorySpec, ModelRef, RAGRef, ToolRef


SYSTEM = """You are a portfolio analyst. Inputs: positions, recent fills, ledger
balance over time, exposure breakdown. Output JSON:

{
  "summary": "...",
  "risk_concentrations": [...],
  "diversification_score": 0..10,
  "drawdown_attribution": "...",
  "regulatory_exposure": [...],   // tickers with notable CFPB/FDA/USPTO signals
  "next_actions": [...],
  "rationale": "..."
}
"""


def build_portfolio_analyst_spec() -> AgentSpec:
    return AgentSpec(
        name="analysis.portfolio",
        role="portfolio_analyst",
        description="Interpret portfolio aggregate performance + risk.",
        system_prompt=SYSTEM,
        model=ModelRef(provider="ollama", model="", tier="deep", temperature=0.15),
        tools=[
            ToolRef(name="metrics"),
            ToolRef(name="ledger"),
            ToolRef(name="risk_check"),
            ToolRef(name="hierarchy_browse"),
            ToolRef(name="regulatory_lookup"),
            ToolRef(name="annotation"),
        ],
        memory=MemorySpec(kind="redis_hybrid", role="analysis.portfolio", working_max=64),
        rag=[
            RAGRef(
                levels=["l0", "l1", "l2"],
                orders=["first", "second"],
                per_level_k=4,
                final_k=10,
            ),
        ],
        guardrails=GuardrailSpec(require_rationale=True, cost_budget_usd=0.75),
        max_cost_usd=0.75,
        max_calls=15,
        annotations=["analysis", "portfolio"],
    )
