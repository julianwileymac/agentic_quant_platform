---
title: 'ADR 008 — Bot Event Sourcing (PostgreSQL, monthly-partitioned)'
summary: 'Each running bot generates a stream of decision/order/fill/snapshot events. To support:'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# ADR 008 — Bot Event Sourcing (PostgreSQL, monthly-partitioned)

**Status:** Accepted (QuantBot Platform v0.2.0)
**Date:** 2026-05-24
**Decision drivers:** Blueprint §H; AGENTS rules 3, 6, 34.

## Context

Each running bot generates a stream of decision/order/fill/snapshot
events. To support:

1. Restart recovery without losing state.
2. Time-travel debugging ("show me the position at 14:32:11 yesterday").
3. Regulatory audit (RTS 6 Article 17(3) real-time reconciliation).
4. Replay-based regression testing of strategy changes.

...we need an append-only, queryable event log per bot.

## Decision

- **Backend:** PostgreSQL, the same database that already holds
  `bots` / `bot_versions` / `bot_deployments`. No new technology to
  operationalize.
- **Partitioning:** `bot_events` is `PARTITION BY RANGE (recorded_at)`
  on PostgreSQL with one partition per UTC month. Partition pruning
  keeps queries fast even at billion-row scale (per documented
  PostgreSQL event-sourcing patterns).
- **Sequence numbers:** monotonic per bot (`bot_id`, `seq_no`). The
  `EventStore` writer keeps the next-available `seq_no` in memory
  and increments on each append; on restart it reads `max(seq_no)`
  + 1.
- **Snapshots:** periodic `bot_snapshots` rows act as replay anchors.
  On startup the kernel reads the latest snapshot and replays events
  with `seq_no > snapshot.seq_no` rather than from zero.
- **Tenancy:** every row carries `owner_user_id` / `workspace_id` /
  `project_id` / `experiment_id` / `test_id` per AGENTS rule 34;
  the existing `LedgerWriter._stamp` populates them automatically
  from the active `RequestContext`.
- **GIN index** on `bot_events.event_data` (JSONB) so ad-hoc queries
  like "all fills with `fee_currency=USDT`" stay fast.

## Alternatives considered

| Option | Why rejected |
| --- | --- |
| Kafka log only | Not random-access; harder to query for time-travel; we already have Postgres |
| TimescaleDB hypertable | Extra dependency to operate; partition pruning on plain Postgres is sufficient at our scale |
| One table per bot | Operational nightmare at >100 bots; partition pruning gives us the same query performance with one schema |
| Iceberg-only | Lakehouse latency too high for the kernel's restart path |

## Iceberg interplay (Rule 3)

`bot_events` is **operational** state — kernel writes happen on the
hot path. **Analytical** writes (trajectory exports, signal series,
gold-tier aggregates) still go through `iceberg_catalog.append_arrow`
per AGENTS rule 3; the operational + analytical paths are deliberately
separate to keep the kernel's write latency predictable.

## Consequences

- **+** Restart recovery is O(snapshot + events_since_snapshot) rather
  than O(all_events).
- **+** Time-travel debugging is one Postgres query.
- **+** No new infrastructure to operate.
- **−** Monthly partitioning requires a Celery beat task to pre-create
  next month's partition (Phase 12 — Celery wiring deferred to follow-up).
- **−** GIN index churns on high-volume JSONB inserts; mitigated by
  the `EventStore` batching writes every `flush_interval_s`.

## References

- [alembic/versions/0058_bot_event_sourcing.py](../../../alembic/versions/0058_bot_event_sourcing.py)
- [aqp_bots/state/store.py](../../../aqp_bots/state/store.py)
- [aqp_bots/state/replay.py](../../../aqp_bots/state/replay.py)
