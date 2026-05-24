# ADR 007 — QuantBot Latency Classes

**Status:** Accepted (QuantBot Platform v0.2.0)
**Date:** 2026-05-24

## Context

Bots in the QuantBot Platform span a 6-order-of-magnitude latency
range: sub-millisecond market makers next to once-a-day rebalancers
next to event-driven MEV searchers. We need a taxonomy that:

1. Maps onto a concrete Kubernetes scheduling primitive (different
   primitives for different tiers).
2. Constrains where each bot can be scheduled (HFT bots only on
   dedicated NUMA-pinned nodes).
3. Tells the operator what hardware features to validate (HugePages,
   SR-IOV, PTP).
4. Drives the alert SLO thresholds (1 ms P99 vs 1 µs P99).

## Decision

Five canonical latency classes (`Frequency` StrEnum):

| Class | Latency target | K8s primitive | Special hardware |
| --- | --- | --- | --- |
| `hft`   | < 1 ms tick-to-trade | DaemonSet on tainted nodes (1 bot / node) | NUMA pinning, HugePages, SR-IOV, PTP |
| `mid`   | 1 ms – 1 s | StatefulSet (stateful) | None |
| `low`   | 1 s – 1 min | Deployment (stateless) | None |
| `eod`   | batch / daily | CronJob | None |
| `event` | event-driven | Deployment (long-running consumer) | None |

The `Frequency.HFT` Pydantic validator enforces:

- `needs_numa_pinning == True`
- `expected_p99_tick_to_trade_us` is set

These are required because operator scheduling decisions are
made off the capability declaration; an HFT bot without NUMA
pinning would silently land on a shared node and violate the
RTS 25 1-microsecond timestamp granularity requirement.

## Python ceiling (caveat #1 from blueprint)

Pure Python + Cython targets **100-500 µs** for non-kernel-bypass
HFT. The Aeron / Google Cloud benchmark (weareadaptive.com, 2024)
reports 57 µs default / 18 µs with kernel-bypass at 100k msg/s — and
that's a Java baseline. Bots requiring sub-100 µs MUST use the Rust
escape hatch in `aqp_bots/hft/escape_hatch.py`. The architecture
explicitly documents this so we don't over-promise.

## Consequences

- **+** Operator scheduling is deterministic from the spec.
- **+** Alert SLOs auto-derive from the latency class.
- **−** Adding a tier in the future (e.g. `ultra_hft` for sub-100 µs)
  requires a new enum value and operator handler.

## References

- [aqp_bots/spec.py — Frequency enum](../../../aqp_bots/spec.py)
- [aqp_bots/hft/](../../../aqp_bots/hft/)
- [Commission Delegated Regulation (EU) 2017/574 — RTS 25 clock sync]
