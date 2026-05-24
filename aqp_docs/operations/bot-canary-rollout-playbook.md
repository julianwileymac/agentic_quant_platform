# Bot Canary Rollout Playbook

> When to use it, how to read the dashboards, how to abort, and how
> to tune false positives.

## When to use a canary

- Any strategy code change (new alpha, new portfolio constructor, new
  execution algo).
- Any adapter change (new venue, new FIX session config, new on-chain
  RPC endpoint).
- Any risk-policy threshold loosening.
- **Not** for: spec-only documentation updates, image rebuilds that
  don't change behavior, k8s manifest tweaks that don't change pod
  spec.

## Steps

### 1. Author the canary

Edit the bot's GitOps values file:

```yaml
# values-bot-mm-aapl.yaml
bot:
  variant: canary           # mutated label drives the Rollouts split
  botSpec:
    # New strategy parameters here.
```

### 2. Open a PR

Required CI checks:

- [ ] `tests/bots` green
- [ ] `python -m aqp_bots.cli validate <slug>` passes
- [ ] `python -m aqp_bots.cli conformance <slug>` passes
- [ ] `python -m aqp_bots.cli stress <slug>` passes
- [ ] Trivy scan: no CRITICAL/HIGH CVEs on the new image
- [ ] Cosign signature attached

### 3. Argo CD syncs the Rollout

The CanaryRollout CR mutates from `currentStep=0` to `currentStep=1`
when the new image lands. Traffic shifts to 10%.

### 4. Watch the AnalysisTemplate results

```bash
kubectl argo rollouts get rollout bot-mm-aapl
```

Expected output:

```
Status:        ✔ Healthy
Strategy:      Canary
  Step:        1/5
  SetWeight:   10
  Current:     stable=18 canary=2
```

The Prometheus dashboard `Bot Canary - <slug>` shows three traces:

- `quantbot_realized_pnl_usd{variant="canary"}` vs `{variant="stable"}`
- `quantbot_orders_rejected_total / quantbot_orders_total` per variant
- `histogram_quantile(0.99, quantbot_tick_to_trade_seconds_bucket)` per variant

### 5. Promotion vs abort

- **Auto-promote:** if all three AnalysisTemplates pass the configured
  windows, the rollout advances to the next step automatically.
- **Auto-abort:** any AnalysisTemplate failure aborts the rollout
  and reverts traffic to 100% stable. Slack/PagerDuty alert
  `BotErrorRateHigh` or `BotPnLDrawdownCritical` fires.
- **Manual abort:**

  ```bash
  kubectl argo rollouts abort bot-mm-aapl
  ```

- **Manual promote (for an indefinite pause step):**

  ```bash
  kubectl argo rollouts promote bot-mm-aapl
  ```

## Tuning false positives

If you observe a healthy canary aborting frequently:

1. **Tighten the metric query first.** Move from `rate(...[1m])` to
   `rate(...[5m])`; use a robust quantile (e.g. `histogram_quantile(0.99,
   sum by (le) (rate(...[5m])))`).
2. **Lengthen the window.** Bump `count` from 30 to 60.
3. **Only THEN relax the success condition.** Don't relax `pnlVsStableMinUsd`
   from `-50` to `-150` without first investigating the variance source.

Per blueprint caveat #7: if the canary AnalysisTemplate false-positive
rate exceeds 10% (good canaries aborted by noisy metric), tighten the
metric query before relaxing the success condition.

## Hard abort: emergency

If the canary is in `Progressing` state but you see live PnL bleeding
faster than the abort criterion would catch:

```bash
# Three-scope kill switch — engaged at bot scope.
kubectl apply -f - <<EOF
apiVersion: quantbot.io/v1
kind: KillSwitch
metadata:
  name: emergency-mm-aapl-canary
  namespace: aqp-bots
spec:
  scope: bot
  target: mm-aapl
  mode: flatten
  reason: "emergency canary bleed"
EOF
```

This bypasses the rollout reconciler — every pod with
`quantbot.io/bot-slug=mm-aapl` halts within `poll_interval_s` (5s).
