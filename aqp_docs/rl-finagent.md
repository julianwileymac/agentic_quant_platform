# RL FinAgent Layered Reflection Adapter (Phase 10)

Reference docs for the FinAgent multimodal LLM-hybrid agent ported
into `aqp_rl` per Zhang AAAI 24.

## Five-stage cascade

| # | Stage | YAML | Purpose |
| --- | --- | --- | --- |
| 1 | `low_intelligence` | [`configs/agents/finagent/low_intelligence.yaml`](../configs/agents/finagent/low_intelligence.yaml) | Factual 2-3 sentence market read |
| 2 | `high_intelligence` | [`configs/agents/finagent/high_intelligence.yaml`](../configs/agents/finagent/high_intelligence.yaml) | Strategic outlook + bias |
| 3 | `low_reflection` | [`configs/agents/finagent/low_reflection.yaml`](../configs/agents/finagent/low_reflection.yaml) | 1-bar post-mortem |
| 4 | `high_reflection` | [`configs/agents/finagent/high_reflection.yaml`](../configs/agents/finagent/high_reflection.yaml) | k-bar strategic post-mortem |
| 5 | `decision` | [`configs/agents/finagent/decision.yaml`](../configs/agents/finagent/decision.yaml) | Final SELL/HOLD/BUY |

Each stage's LLM call routes through `router_complete` (hard rule
2). The adapter degrades gracefully when the router is unavailable
or any stage fails (defaults to `HOLD`).

## Three tools

| Tool | File | Purpose |
| --- | --- | --- |
| `KlinePlotterTool` | [`aqp/agents/tools/finagent/kline_plotter.py`](../aqp/agents/tools/finagent/kline_plotter.py) | Summarise bars → text |
| `TradingPlotterTool` | [`aqp/agents/tools/finagent/trading_plotter.py`](../aqp/agents/tools/finagent/trading_plotter.py) | Summarise action history → text |
| `StrategyAgentsTool` | [`aqp/agents/tools/finagent/strategy_agents_tool.py`](../aqp/agents/tools/finagent/strategy_agents_tool.py) | Query another RL agent's decision |

## Modules

| File | Class | Purpose |
| --- | --- | --- |
| [`aqp_rl/src/aqp_rl/agents/llm_hybrid_layered.py`](../aqp_rl/src/aqp_rl/agents/llm_hybrid_layered.py) | `LayeredReflectionAdapter` | 5-stage prompt cascade |
| [`aqp_rl/src/aqp_rl/envs/tradesim_multimodal.py`](../aqp_rl/src/aqp_rl/envs/tradesim_multimodal.py) | `MultimodalTradingEnv` | FinAgent-style dict observation |

## Usage

```python
from aqp_rl.agents.llm_hybrid_layered import LayeredReflectionAdapter

adapter = LayeredReflectionAdapter(
    llm_model="ollama/llama3",
    rl_weight=0.5,           # blend 50% with RL backbone
    rl_agent={"class": "ppo_inhouse"},
)
adapter.build(env)
action, _ = adapter.predict(obs)        # int in {0=SELL, 1=HOLD, 2=BUY}

# Between predicts, update the memory so reflection stages have something
# to critique:
adapter.update_realised_pnl(realised_short=0.01, realised_k=0.02)
```

## Hard rule alignment

- Hard rule 2: every LLM call routes through `router_complete`.
- Hard rule 12: each stage is a separate `AgentRuntime` invocation
  (see the YAMLs' `model:` blocks).
- Hard rule 19: adapter registers via `RLComponent` metaclass under
  `rl_alias='finagent_layered'`.

## Acceptance

[Phase 10 tests](../aqp_rl/tests/finagent/) verify:

- 5 stages invoke `router_complete` exactly once each.
- Decision JSON parsed correctly into action int.
- Memory updates persist between calls.
- Cascade degrades to HOLD on LLM failure.
- All 3 tools handle valid + empty inputs.
