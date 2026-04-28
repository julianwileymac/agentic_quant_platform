"""Trader agent: emits trading signals from windowed indicators + fundamentals RAG."""
from __future__ import annotations

from aqp.agents.spec import AgentSpec, GuardrailSpec, MemorySpec, ModelRef, RAGRef, ToolRef


SYSTEM = """You are a disciplined trader agent. For every input symbol you produce
ONE structured signal in JSON:

{
  "vt_symbol": "...",
  "as_of": "YYYY-MM-DDTHH:MM:SSZ",
  "action": "buy" | "sell" | "hold",
  "confidence": 0..1,
  "horizon": "intraday" | "1d" | "5d" | "20d",
  "size_hint_pct": 0..1,    // suggested position size as fraction of equity
  "stop_loss_pct": 0..1,    // suggested stop-loss
  "take_profit_pct": 0..1,
  "rationale": "...",
  "evidence": [{"corpus": "...", "doc_id": "...", "snippet": "..."}]
}

Process:
1. Use performance_window for the symbol's recent technical state.
2. Use fundamentals_snapshot for the latest valuation.
3. Use rag_query against L2 financial_ratios + L1 performance to compare
   the candidate to historically successful setups.
4. Respect the kill_switch tool — if it returns "engaged" you MUST emit "hold".
5. Use risk_check to verify the proposed size_hint is allowed.

You do NOT execute trades; you emit signals only. Do NOT hallucinate
numbers — if a tool fails, lower confidence and explain in rationale.
"""


def build_signal_emitter_spec() -> AgentSpec:
    return AgentSpec(
        name="trader.signal_emitter",
        role="signal_emitter",
        description="LLM trader that emits structured signals from windowed RAG context.",
        system_prompt=SYSTEM,
        model=ModelRef(provider="ollama", model="", tier="quick", temperature=0.15),
        tools=[
            ToolRef(name="performance_window"),
            ToolRef(name="fundamentals_snapshot"),
            ToolRef(name="rag_query"),
            ToolRef(name="risk_check"),
            ToolRef(name="kill_switch"),
            ToolRef(name="annotation"),
        ],
        memory=MemorySpec(kind="redis_hybrid", role="trader.signal_emitter", working_max=64),
        rag=[
            RAGRef(
                levels=["l1", "l2"],
                orders=["first", "second"],
                corpora=["bars_daily", "performance", "financial_ratios"],
                per_level_k=4,
                final_k=10,
            ),
            RAGRef(
                levels=["l0"],
                orders=["first"],
                corpora=["decisions"],
                per_level_k=5,
                final_k=5,
            ),
        ],
        guardrails=GuardrailSpec(
            require_rationale=True,
            min_confidence=0.0,
            cost_budget_usd=0.25,
            rate_limit_per_minute=120,
            forbidden_terms=["guaranteed", "risk free"],
        ),
        max_cost_usd=0.25,
        max_calls=10,
        annotations=["trader", "signal"],
    )
