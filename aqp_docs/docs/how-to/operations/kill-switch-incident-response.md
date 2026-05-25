---
title: 'Kill Switch Incident Response'
summary: '| Scope | What it halts | Typical use | | --- | --- | --- | | `bot` | One Pod (one bot slug) | A single bot is misbehaving | | `fleet` | Every bot in a fleet | A fleet-wide alpha goes stale | | `platf...'
owner: sre-team
last_reviewed: 2026-05-25
audience: both
---

# Kill Switch Incident Response

> Three-scope kill switch (bot / fleet / platform). Quarterly drill
> required per blueprint caveat #7.

## Scopes

| Scope | What it halts | Typical use |
| --- | --- | --- |
| `bot` | One Pod (one bot slug) | A single bot is misbehaving |
| `fleet` | Every bot in a fleet | A fleet-wide alpha goes stale |
| `platform` | Every bot on the platform | Emergency — venue outage, regulatory action |

## Engage

### Via CRD (preferred — leaves audit trail)

```bash
kubectl apply -f - <<EOF
apiVersion: quantbot.io/v1
kind: KillSwitch
metadata:
  name: emergency-<reason>
  namespace: aqp-bots
spec:
  scope: bot                # bot | fleet | platform
  target: mm-aapl           # bot slug / fleet name / "platform"
  mode: flatten             # cancel | flatten | freeze
  reason: "venue outage; halting until investigation complete"
  ttl: 1h
EOF
```

### Via the REST kill-switch fan-out (UI button)

The operator UI's `KillSwitch` topbar component calls a sequence of
halt endpoints in parallel:

- `POST /agents/halt`
- `POST /quant-agents/halt`
- `POST /paper/stop-all`
- `POST /bots/halt-all`   ← halts every active bot deployment
- `POST /rl/halt-all`
- `POST /workflows/halt`

This is the equivalent of `KillSwitch.scope=platform` from the operator
side. Use it when GitOps reconciliation is too slow (the CRD path can
take up to `poll_interval_s` seconds; the REST fan-out is instant).

### Via the redundant Redis polling channel (last resort)

If the Argo CD reconciler is unhealthy AND the REST API is unreachable:

```bash
# Directly set the kill switch key in the bots namespace's Redis.
kubectl exec -n aqp-bots redis-master-0 -- \
  redis-cli SET 'aqp:bots:killswitch:platform:platform' 'manual-emergency'
```

Each bot polls this key every 5 seconds (configurable via
`KillSwitchV2.poll_interval_s`) and halts when set. This is the
fallback documented in blueprint caveat #7.

## Release

### Via CRD

```bash
kubectl delete killswitch emergency-<reason> -n aqp-bots
```

### Via Redis (matching the last-resort engage)

```bash
kubectl exec -n aqp-bots redis-master-0 -- \
  redis-cli DEL 'aqp:bots:killswitch:platform:platform'
```

## Verify

```bash
# CRD view:
kubectl get killswitches -A
# Status:
kubectl get killswitches -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.engaged}{"\n"}{end}'
# Redis view:
kubectl exec -n aqp-bots redis-master-0 -- \
  redis-cli --scan --pattern 'aqp:bots:killswitch:*'
# Affected bots (operator status):
kubectl get bots -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.killSwitchEngaged}{"\t"}{.status.killSwitchReason}{"\n"}{end}'
```

## Quarterly drill (caveat #7)

The blueprint mandates a **quarterly drill** because the worst time
to discover the kill switch is broken is during a real incident.

### Drill protocol

1. Schedule a 15-minute window during low-activity hours.
2. Engage `scope=platform` via the CRD path.
3. Verify every bot in `kubectl get bots -A` transitions to
   `status.phase=Draining` within 10 seconds.
4. Verify every bot reaches `Stopped` within 30 seconds (HFT) or
   300 seconds (everything else).
5. Release the kill switch.
6. Verify bots auto-restart (their Deployments / StatefulSets reconcile).
7. Repeat with the REST fan-out path.
8. Repeat with the Redis fallback path.
9. Record the drill in the next RTS 6 validation report's
   `kill_switch_drills` evidence section.

Failure of any of the three paths is a P1 incident. Fix before the
drill window closes.

## Common failure modes

- **Operator pod is down.** Symptom: `KillSwitch` CR created but
  bots don't halt within `poll_interval_s`. Mitigation: the Redis
  polling fallback bypasses the operator entirely.
- **Redis pod is down.** Symptom: neither operator nor polling
  fallback works. Mitigation: at least one of the operator's
  in-memory CR watcher or the REST API fan-out path will still
  halt bots; if all three fail simultaneously, escalate to manual
  `kubectl scale deployment/bot-* --replicas=0`.
- **Redis Pub/Sub vs SET-key drift.** `KillSwitchV2.poll_interval_s`
  defines the upper bound on the polling fallback's latency; if the
  pub/sub channel is dropping messages, polling still works after at
  most one interval.
