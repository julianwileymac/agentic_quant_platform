---
title: 'Tutorials'
summary: 'Runnable walkthroughs for every AQP surface. Pyodide + StackBlitz WebContainers in your browser.'
owner: docs-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 1
---

# Tutorials

Runnable, learning-oriented walkthroughs. Each tutorial assumes the
[quickstart](../intro/quickstart.md) has succeeded.

Python snippets execute via Pyodide directly in your browser; full
project setups open in StackBlitz WebContainers. Both are sandboxed
and never reach the production cluster.

## Tutorial catalogue

- **[First backtest](./first-backtest.md)** — author a momentum
  strategy, run it through `EventDrivenBacktester`, inspect the
  `backtest_runs` ledger row, render a tearsheet.
- **[First bot](./first-bot.md)** — wrap the strategy in a
  `TradingBot` spec, snapshot the version, run a paper session.
- **[First RL experiment](./first-rl-experiment.md)** — author an
  `RLExperimentSpec`, train via SB3 PPO, replay from the Iceberg
  trajectory store.
- **[First agent workflow](./first-agent-workflow.md)** — compose a
  three-node LangGraph (Research → Selection → Trader), run it
  through `AgentRuntime`, inspect the agent_runs_v2 ledger.
- **[First paper trading session](./first-paper-trading-session.md)** —
  attach the bot to the paper broker, watch the WebSocket frames,
  trigger the kill switch.

Each tutorial includes:

1. A "Why" section explaining what you are about to learn.
2. A canonical reference to the deeper concept doc.
3. Inline runnable code.
4. A "Verify" checklist at the end.
5. A "What next" pointer.

## Conventions for these tutorials

- **One concept per page.** If a tutorial gets too long, split it
  and link the second page.
- **Verify everything.** Every code block produces an observable
  effect — a JSON response, a ledger row, a WebSocket frame.
- **Show the failure mode.** Each tutorial documents at least one
  expected error and how to recover.
