---
title: 'Your first bot'
summary: 'Wrap a backtested strategy in a TradingBot spec, snapshot the immutable version, run a paper session.'
owner: docs-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 3
---

# Your first bot

Goal: take the strategy from [first-backtest](./first-backtest.md)
and wrap it in a `BotSpec` so it can be paper-traded, deployed to
Kubernetes, or chat-driven — all from a single immutable contract.

## Why

A bot is the smallest deployable unit in AQP. It aggregates the
universe + strategy + engine + ML models + agents + RAG + risk
limits + metrics into one hash-locked spec that
[`BotRuntime`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_bots/runtime.py)
can drive through every lifecycle stage. See
[Concept: bots](../concepts/agentic/bots.md).

## Step 1 — author the BotSpec

Create `configs/bots/my_first_bot.yaml`:

```yaml
name: MyFirstBot
kind: trading
description: 'First-bot tutorial — wraps MyFirstMomentum.'
strategy_config: configs/strategies/my_first_strategy.yaml
engine: event_driven
risk:
  max_position_pct: 0.5
  max_daily_loss_pct: 0.02
  kill_switch_attached: true
metrics:
  - sharpe
  - sortino
  - max_drawdown
  - hit_rate
deploy_target: paper
```

## Step 2 — snapshot the spec

```powershell
curl -X POST http://localhost:8000/bots \
    -H "Content-Type: application/json" \
    -d @configs/bots/my_first_bot.yaml
```

This persists a `bot_versions` row with the hash-locked spec. The
response includes the `bot_id` (use this everywhere downstream)
and the `spec_hash`. Different content → different hash → new
version row; the old version stays intact for replay.

## Step 3 — backtest the bot

```powershell
curl -X POST http://localhost:8000/bots/<bot_id>/backtest \
    -d '{"start":"2024-01-01","end":"2024-06-30"}'
```

Same engine as the prior tutorial, but the bot's risk overlays
apply. The ledger row in `backtest_runs` carries the `bot_id` so
you can correlate.

## Step 4 — paper-trade the bot

```powershell
curl -X POST http://localhost:8000/bots/<bot_id>/paper \
    -d '{"starting_cash":100000}'
```

`BotRuntime` creates a `paper_trading_runs` row and attaches the
bot to the paper broker session loop in
[aqp/trading/paper_trading.py](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/trading/paper_trading.py).

Watch the live WebSocket feed:

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/paper/<paper_run_id>");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

You will see fills, position updates, and equity-curve points
streaming through the canonical progress-frame envelope.

## Step 5 — halt the bot

The bot has the kill switch attached (see Step 1 — `kill_switch_attached: true`).
Trigger a halt:

```powershell
curl -X POST http://localhost:8000/bots/halt-all
```

Every paper session under every bot stops within ~250 ms.

## Verify

- [ ] `bot_versions` row visible with a `spec_hash`.
- [ ] `backtest_runs` row tagged with your `bot_id`.
- [ ] `paper_trading_runs` row visible.
- [ ] WebSocket feed delivered frames.
- [ ] Kill switch halted the bot.

## What next

- [Concept: bots](../concepts/agentic/bots.md) — the full bot
  contract + deployment targets (paper / k8s / backtest_only).
- [Recipe: promote a bot to paper](../how-to/recipes/promote-a-bot-to-paper.md) —
  same thing, but as a how-to.
- [Tutorial: first paper trading session](./first-paper-trading-session.md) —
  go deeper on the paper-trading lifecycle and risk overlays.
