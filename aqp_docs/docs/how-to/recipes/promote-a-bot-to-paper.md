---
title: 'Recipe: promote a bot to paper'
summary: 'Take a backtested bot and start a paper-trading session, respecting the paper-metadata gate.'
owner: trading-team
last_reviewed: 2026-05-25
audience: both
---

# Recipe: promote a bot to paper

```powershell
# 1. Snapshot the bot (idempotent — same hash returns same version).
curl -X POST http://localhost:8000/bots `
    -H "Content-Type: application/json" `
    -d @configs/bots/my-bot.yaml

# 2. Backtest the bot (gates require a recent backtest_runs row).
curl -X POST http://localhost:8000/bots/<bot_id>/backtest `
    -d '{"start":"2024-01-01","end":"2024-06-30"}'

# 3. Promote to paper.
curl -X POST http://localhost:8000/bots/<bot_id>/paper `
    -d '{"starting_cash":100000,"duration_minutes":60}'
```

## The paper-metadata gate

`POST /bots/<id>/paper` runs [paper_metadata_gate](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/trading/paper_metadata_gate.py)
before launching the session. It rejects when:

- No `backtest_runs` row for the bot, or it is older than 7 days.
- `sharpe < 0.5` on the latest backtest.
- `max_drawdown > 0.20`.
- `risk.kill_switch_attached != true`.
- The bot's universe contains a symbol that isn't in the active
  data plane.

Override the gate via the `--force` flag on `/bots/<id>/paper`
only with explicit approval. The audit ledger records who forced it
and why.

## Risk + kill switch

The session inherits the bot's `risk:` block. Trigger a stop:

```powershell
curl -X POST http://localhost:8000/paper/stop-all
# or use the topbar kill switch in the Vite UI
```

## Deeper reads

- [Tutorial: first paper trading session](../../tutorials/first-paper-trading-session.md)
- [Concept: paper trading](../../concepts/trading/paper-trading.md)
- [Concept: paper metadata gate](../../concepts/trading/paper-metadata-gate.md)
- [Runbook: kill-switch incident response](../../how-to/operations/kill-switch-incident-response.md)
