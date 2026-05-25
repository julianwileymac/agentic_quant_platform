---
title: 'Runbook — quota-exhaustion'
summary: '1. Open the rate-limit dashboard at `/data/ratelimit`. Find the over-consuming `(user_id, service, key_id)`. 2. Inspect the `rl_ledger` partition for the last hour:'
owner: sre-team
last_reviewed: 2026-05-25
audience: both
---

# Runbook — quota-exhaustion

A bucket has fired `AQPRatelimitBucketAt80Percent`,
`AQPRatelimitBucketAt95Percent`, or `AQPRatelimitBucketExhausted`.

## Diagnosis (5 min)

1. Open the rate-limit dashboard at `/data/ratelimit`. Find the
   over-consuming `(user_id, service, key_id)`.
2. Inspect the `rl_ledger` partition for the last hour:

   ```sql
   SELECT decision, count(*), sum(tokens_consumed)
     FROM rl_ledger
    WHERE ts > now() - interval '1 hour'
      AND key_id = :key_id
    GROUP BY decision;
   ```

3. Cross-reference `audit_log` for the calling `tool_id` —
   `data.ingest.materialize` or `data.ingest.preview_source` are
   the usual culprits.

## Decision tree (10 min)

| Cause | Action |
| --- | --- |
| Misconfigured backfill | Tell the operator to cancel via `aqp materialize cancel <reservation_id>`. The reservation auto-releases. |
| Vendor downgrade | Mint a higher-tier key via `aqp keys mint --service polygon --rps 100 --burst 1000`. |
| Stuck connector loop | `aqp ratelimit status --key-id <id>` shows the call rate; halt the offending Dagster sensor via the topbar kill-switch. |
| Legitimate traffic | Raise the policy via `data.ratelimit.policy.update` (Tier-P + step-up MFA). |

## Recovery (15 min)

1. Once the cause is addressed, the bucket refills at the policy's
   `refill_rate`; no manual reset is required.
2. If the operator wants an immediate reset, run the Phase 6
   admin script that explicitly DELs the bucket key:

   ```bash
   aqp ratelimit admin reset --user-id <uid> --service polygon --key-id primary
   ```

3. Verify recovery in Grafana:

   ```
   rl_bucket_remaining{service="polygon.aggregates"} > 50
   ```

## Postmortem

Every quota-exhaustion alert that requires manual intervention
must produce a postmortem PR within 72 hours. Template:
`aqp_docs/docs/how-to/runbooks/templates/postmortem.md` (to be authored).
