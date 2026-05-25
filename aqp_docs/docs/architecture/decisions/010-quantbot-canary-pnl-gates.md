---
title: 'ADR 010 — Canary Rollout PnL Gates'
summary: 'Strategy changes (new alpha model, new portfolio constructor, new execution algo) are the highest-leverage and highest-risk changes the platform makes. Rolling them across the entire fleet at once is ...'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# ADR 010 — Canary Rollout PnL Gates

**Status:** Accepted (QuantBot Platform v0.2.0)
**Date:** 2026-05-24

## Context

Strategy changes (new alpha model, new portfolio constructor, new
execution algo) are the highest-leverage and highest-risk changes the
platform makes. Rolling them across the entire fleet at once is
unacceptable; bake time is mandatory. Argo Rollouts canary lets us
shift weight gradually, but the canary needs **automated abort
criteria** beyond the standard liveness/readiness probes — a bot can
be `Ready=True` and still be hemorrhaging money.

## Decision

Three AnalysisTemplates gate every canary promotion step:

1. **`bot-canary-pnl`** — realised PnL of the canary vs the stable
   variant. Default success condition:
   `canary_realized_pnl - stable_realized_pnl >= -50 USD` over 6 ×
   5-minute windows (30-minute total).
2. **`bot-reject-rate`** — fraction of orders that are rejected
   (by venue or by pre-trade risk). Default success condition:
   `<= 1%` over 30 × 1-minute windows.
3. **`bot-p99-latency`** — P99 tick-to-trade latency. Default
   success condition: `<= 1 ms` (HFT canaries override to `<= 100 µs`).

The canary spec follows the standard Argo Rollouts pattern:

```
steps:
  - setWeight: 10
  - pause: { duration: 30m }
  - analysis: { templates: [bot-canary-pnl, bot-reject-rate, bot-p99-latency] }
  - setWeight: 50
  - pause: { duration: 1h }
  - analysis: { templates: [bot-canary-pnl, bot-reject-rate, bot-p99-latency] }
  - setWeight: 100
```

Failure of any AnalysisTemplate **aborts the rollout** and reverts
traffic to the stable version. The operator additionally watches
the `BotPnLDrawdownCritical` PrometheusRule; if the canary bleeds
more than `maxAbortRolloutPnlBleedUsd` (default $500) the alert
auto-fires a `KillSwitch` CR which halts the canary instantly —
this protects against the case where the rollout abort itself takes
longer than the bleed.

## Default thresholds rationale

The $50 PnL floor is intentionally generous for the initial canary
window — it admits some short-term variance that is statistically
normal between two variants of the same strategy. The harder $500
bleed threshold (drawdown alert) is what catches truly broken canaries
within seconds.

Per blueprint caveat (canary false-positive rate): if good canaries
are routinely aborted on noisy metrics, tighten the metric query
**first** (more samples, longer windows, robust quantiles) before
relaxing the success condition.

## Consequences

- **+** Strategy changes have an automated bake-time gate.
- **+** The same canary pattern works for both stateless mid-frequency
  bots and HFT bots (only the latency threshold differs).
- **−** AnalysisTemplate thresholds need per-strategy calibration —
  a market-making bot's "good" reject rate is higher than a stat-arb
  pair's "good" reject rate.
- **−** A canary that's still warming up may not yet have produced
  enough orders for the metrics to be meaningful; we mitigate with
  the initial 30-minute pause before the first analysis check.

## References

- [aqp_platform/deployments/argocd/rollouts/](../../../aqp_platform/deployments/argocd/rollouts/)
- [aqp_platform/deployments/kubernetes/bots-operator/prometheus-rules.yaml](../../../aqp_platform/deployments/kubernetes/bots-operator/prometheus-rules.yaml)
