# Trader Agents

The spec-driven trader (`trader.signal_emitter`) coexists with the
existing TradingAgents-style debate trader under
[aqp/agents/trading/](../aqp/agents/trading/). The new one is
deliberately simpler — one structured signal per call — so it can
slot into the LangGraph pipeline and the agentic backtest loop.

## Spec

[aqp/agents/trader/signal_emitter.py](../aqp/agents/trader/signal_emitter.py).

## RAG

- **L1 / L2** — `bars_daily`, `performance`, `financial_ratios` for
  windowed indicator + fundamentals context.
- **L0** — `decisions` for prior-trade reflection (paper RAG#0).

## Output schema

```json
{
  "vt_symbol": "AAPL.NASDAQ",
  "as_of": "2026-04-27T20:00:00Z",
  "action": "buy" | "sell" | "hold",
  "confidence": 0..1,
  "horizon": "intraday" | "1d" | "5d" | "20d",
  "size_hint_pct": 0..1,
  "stop_loss_pct": 0..1,
  "take_profit_pct": 0..1,
  "rationale": "...",
  "evidence": [{"corpus": "...", "doc_id": "...", "snippet": "..."}]
}
```

## Safety

- Honors the runtime kill switch (Redis key
  `settings.risk_kill_switch_key`); when engaged the agent MUST emit
  `"hold"`.
- `risk_check` validates the proposed `size_hint_pct`.
- Guardrail caps cost at 0.25 USD / call by default.

## REST

```
POST /agents/trader/signal              — emit one signal (sync emit + task id)
POST /agents/trader/sync                — pure synchronous run
POST /agents/trader/backtest-with-agent — kick off agentic backtest
```

## YAML

[configs/agents/trader_signal_emitter.yaml](../configs/agents/trader_signal_emitter.yaml).
