---
title: 'Runbook — Disaster Recovery: full restore (<30 min)'
summary: '1. The Redis primary in `aqp-system` is gone. The `redis-master.aqp-system.svc` Service points to no pod. 2. Spin a fresh Redis pod:'
owner: sre-team
last_reviewed: 2026-05-25
audience: both
---

# Runbook — Disaster Recovery: full restore (<30 min)

Restores the Phase 6 reliability surface from S3 in three layers.

## Layer 1: rate-limit Redis (5 min)

1. The Redis primary in `aqp-system` is gone. The
   `redis-master.aqp-system.svc` Service points to no pod.
2. Spin a fresh Redis pod:

   ```bash
   kubectl -n aqp-system scale statefulset/redis --replicas=1
   ```

3. The Lua scripts re-register lazily on the first `Check` call
   (see `RedisTokenBucketStrategy._ensure_initialised` —
   `EVALSHA` failure paths fall back to `EVAL` + re-register).
4. Buckets that were drained in the previous Redis are now full
   again; **this is intentional**. The audit log captures every
   token consumed pre-incident; the operator can replay the
   ledger to rebuild bucket state if compliance requires it.

## Layer 2: audit log (10 min)

1. The `audit_log` table is hash-chain-protected (trigger from
   Alembic 0079). The S3 export (Celery beat task
   `aqp_ratelimit.tasks.ledger_export.export_ledger_window`)
   carries every row in append-only JSONL form.
2. Restore the latest window:

   ```bash
   aqp ratelimit admin restore-ledger \
     --bucket aqp-audit-archive \
     --since 2026-05-01 \
     --until 2026-05-24
   ```

3. The `enforce_audit_log_hash_chain` Postgres trigger validates
   every restored row against its predecessor; on violation the
   restore aborts and surfaces the exact mismatched hex digest.

## Layer 3: dbt-loom manifest registry (10 min)

1. The `s3://aqp-dbt-manifests` bucket is the source of truth
   for cross-project `ref()` lookups.
2. Restore the latest manifest per project:

   ```bash
   aqp deploy restore-dbt-manifests \
     --env prod \
     --to-bucket aqp-dbt-manifests-restored
   ```

3. Update the `loom.yml` in each team project to point at the
   restored bucket name; downstream `dbt parse` succeeds with
   the rehydrated manifests.

## Phase-gate verification

The full DR test must complete in < 30 min wall-clock.
`tests/chaos/test_dr_restore.py` orchestrates the three layers
against a fixture cluster + S3 mock and asserts the < 30 min
deadline.
