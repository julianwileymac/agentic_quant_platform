---
title: 'Your first paper trading session'
summary: 'Attach a bot to the paper broker, watch the WebSocket frames, trigger the kill switch.'
owner: trading-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 6
---

# Your first paper trading session

Goal: drive a paper-trading session from the bot you authored in
[first-bot](./first-bot.md). End-to-end: dispatch → fills → kill.

## Why

Paper trading is the highest-fidelity dress rehearsal AQP supports
without putting real money at risk. Same broker abstraction, same
risk overlays, same kill-switch wiring as live trading. The
difference is that fills come from the simulated execution engine
in [aqp/trading/paper_trading.py](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/trading/paper_trading.py).

See [Concept: paper trading](../concepts/trading/paper-trading.md).

## Step 1 — verify the bot is ready

```powershell
curl http://localhost:8000/bots/<bot_id>
```

Confirm the response includes a recent `backtest_runs` reference and
non-zero `sharpe`. The
[paper-metadata-gate](../concepts/trading/paper-metadata-gate.md)
will refuse to start the session otherwise.

## Step 2 — start the session

```powershell
curl -X POST http://localhost:8000/bots/<bot_id>/paper \
    -d '{"starting_cash":100000,"duration_minutes":60}'
```

The response includes `paper_run_id`. The session is now in
the canonical Celery loop; `aqp-worker` polls the broker every
1 second.

## Step 3 — watch the WebSocket

In a browser console:

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/paper/<paper_run_id>");
ws.onmessage = (e) => {
  const frame = JSON.parse(e.data);
  console.log(frame.stage, frame.message, frame.equity, frame.positions);
};
```

You should see:

- `bar.received` — every minute bar.
- `signal.emitted` — when the strategy says "buy" / "sell" / "flat".
- `order.placed` — order goes to the simulated broker.
- `order.filled` — fill comes back; positions update.
- `equity.update` — equity-curve point at the end of each bar.

All frames follow the canonical `{task_id, stage, message,
timestamp, **extras}` envelope per AGENTS rule 4.

## Step 4 — risk + kill switch

The bot's `risk` block (Step 1 of first-bot) is enforced by
[aqp/risk/limits.py::RiskLimits](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/risk/limits.py).
Once any limit is hit, the session emits `risk.halted` and stops.

The topbar kill switch in the Vite UI fans out to:

- `POST /bots/halt-all`
- `POST /paper/stop-all`
- `POST /agents/halt`
- `POST /rl/halt-all`
- `POST /workflows/halt`
- `POST /terraform/halt`
- `POST /quant-agents/halt`

The whole stack stops in under 250 ms.

## Step 5 — inspect the ledger

```sql
SELECT id, bot_id, status, total_pnl, num_fills, started_at, ended_at
FROM paper_trading_runs ORDER BY started_at DESC LIMIT 1;

SELECT order_id, symbol, side, qty, price, filled_at
FROM paper_fills
WHERE paper_run_id = '<from_above>'
ORDER BY filled_at;
```

## Verify

- [ ] WebSocket delivered at least one `order.filled` frame.
- [ ] `paper_trading_runs` row has non-NULL `total_pnl`.
- [ ] Kill switch closed the session.

## What next

- [Concept: paper trading](../concepts/trading/paper-trading.md) — the
  full session loop, broker abstraction, and risk model.
- [Concept: paper metadata gate](../concepts/trading/paper-metadata-gate.md) —
  why some sessions get blocked before they start.
- [How-to: kill switch incident response](../how-to/operations/kill-switch-incident-response.md) —
  the runbook for when the kill switch fires in production.
