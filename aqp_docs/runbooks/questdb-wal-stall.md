# Runbook — QuestDB WAL apply stall

Symptoms:

- `questdb_wal_apply_lag_seconds` Prometheus metric is above 60s.
- New dbt model materialization runs hang on INSERT.
- The QuestDB UI shows `WAL applied = N` is no longer advancing.

## Root cause

A long-running query or external table lock has blocked the WAL
apply worker. The new QuestDB documentation explicitly warns:
"Non-partitioned tables cannot use WAL" — the AQP custom
`questdb_table` materialization forces `PARTITION BY DAY` to
avoid the most common form, but mis-configured external tables
can still trip the apply loop.

## Recovery

1. Identify the offending table from the Prometheus alert label:

   ```
   {table="equities_minute_bars"}
   ```

2. Suspend writers to that table:

   ```bash
   aqp ratelimit admin halt-pool questdb_writer:equities_minute_bars
   ```

3. Resume the WAL apply loop:

   ```sql
   ALTER TABLE equities_minute_bars RESUME WAL;
   ```

4. Once the lag drops back below 5s, lift the writer halt:

   ```bash
   aqp ratelimit admin resume-pool questdb_writer:equities_minute_bars
   ```

## Prevention

The Phase 2 `aqp/dagster/dagster.yaml` reserves a per-table
`questdb_writer:<table>` pool with `limit=1` so concurrent
writers to the same table are impossible. Verify that pool is
present + has `limit=1`.
