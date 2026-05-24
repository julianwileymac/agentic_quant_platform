# Runbook — dbt snapshot deadlock

Symptoms:

- `dbt snapshot` runs queue indefinitely.
- The `dbt_snapshots` Dagster concurrency pool shows 1 slot in use
  but the corresponding run is `CANCELED` or `FAILED`.

## Root cause

Per the Dagster docs: "a single cancelled run will permanently
deadlock all future runs for that pool" unless the
`free_slots_after_run_end_seconds` knob is set on the
`run_monitoring` block.

## Fix (in this order)

1. Confirm `aqp/dagster/dagster.yaml` has

   ```yaml
   run_monitoring:
     enabled: true
     free_slots_after_run_end_seconds: 300
   ```

   If missing, add it + reload the Dagster instance.

2. Manually free the stuck slot:

   ```bash
   dagster instance concurrency reset dbt_snapshots
   ```

3. Verify with the Dagster UI: the pool should show `0 / 1` used.

## Verification chaos test

`tests/chaos/test_snapshot_deadlock_recovery.py` triggers 5
parallel snapshot jobs against a sqlite test target and asserts
that even after one is cancelled the pool recovers within 360s.

## Postmortem

If the deadlock recurs after the canonical fix, the postmortem
must include a Dagster + dbt version pair and a minimal repro
so the upstream issue can be filed.
