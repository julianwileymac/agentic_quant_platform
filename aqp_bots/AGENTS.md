# AGENTS.md

Agent contract for `aqp_bots` (QuantBot Platform v0.2.0).

## Purpose

This boundary owns:

- The Bot abstraction — the smallest fully-addressable, individually-
  deployable, independently-killable unit of trading or research workload.
- The QuantBot Platform: kopf-based Kubernetes operator with 9 CRDs,
  metaclass-driven adapter Protocols (FIX/WS/REST/gRPC/onchain),
  event-sourced state, RTS 6 + SEC 15c3-5 pre-trade risk, Argo Rollouts
  canary integration, and the HFT hot path (Cython SPSC + PTP + NUMA).
- Templates, samples, validation notes, and agent-readable guidance.

## Hard boundaries

1. **Runtime execution goes through `BotRuntime`** (rule 14). The new
   `BotKernel` is reachable only via `BotRuntime.run_kernel()`; do not
   import it from a strategy module or REST route.
2. **Bot specs are immutable once snapshotted.** Changes create new
   `bot_versions` rows via `persist_spec()`. Operator reconciliation
   calls the same function; it never mutates rows.
3. **Bots compose strategy, engine, agent, RAG, paper, and deployment
   references.** Do not reimplement those subsystems in a bot.
4. **Adapters mirror the `KubernetesAdapterMeta` pattern** (rule 28).
   New venue adapters subclass `MarketDataAdapter` / `ExecutionAdapter` /
   `ControlPlaneAdapter`, set `adapter_kind`, and let the metaclass
   register them through `aqp.core.registry.register`.
5. **Workload lifecycle ops go through `WorkloadRuntime`** (rule 45).
   The operator's start/stop/scale/restart paths route through
   `aqp_platform_core.runtime.workload.WorkloadRuntime._run`.
6. **K8s manifests live in `aqp_platform/`.** Per rpi-k8s-governance,
   shared infra manifests live under `aqp_platform/deployments/kubernetes/`;
   never write a new manifest under `rpi_kubernetes/`.
7. **All Iceberg writes** (trajectory snapshots, replay artifacts) go
   through `iceberg_catalog.append_arrow` (rule 3); never raw PyIceberg.
8. **All LLM calls** (LLM-based strategies, multi-agent research bots)
   go through `router_complete` (rule 2).
9. **Templates use real registry aliases and paths that exist today.**
10. **Keep credentials out of sample specs.** Use placeholders and
    documented credential references.

## Hot-path vs config types

- **Hot-path messages** (`schemas/market.py`, `schemas/trading.py`)
  use `msgspec.Struct(gc=False, frozen=True)` — ~12x faster JSON
  decode than Pydantic v2 per the official msgspec benchmarks.
- **Specs / CRDs / manifests** use Pydantic v2 — richer validator
  errors at the API boundary.

Do not mix the two. The kernel never validates hot-path messages
through Pydantic; the operator never reads a CR through msgspec.

## Where changes go

- New sample spec: `templates/{hft,stat_arb,eod,rl,mev,research,trading}/`.
- Bot runtime behavior: this package.
- Bot kernel runtime: `core/`.
- New adapter family: `adapters/{family}/`.
- New execution algo: `execution/ems.py` + register in `_ALGO_REGISTRY`.
- New risk policy: `risk/policies.py` + add to RTS 6 / 15c3-5 mappings
  in `risk/reg/`.
- New CRD: `operator/crds/{name}_cr.py` (Pydantic mirror) +
  `operator/crds/yaml/{name}_crd.yaml` (the CRD itself) +
  `operator/handlers.py` (kopf handler).
- Bot API behavior: `../aqp/api/routes/bots.py`.
- Bot task behavior: `../aqp/tasks/bot_tasks.py`.
- Persistence: `../aqp/persistence/models_bots.py`.
- Migration: `../alembic/versions/0058_bot_event_sourcing.py` (existing)
  or a new immutable migration.
- Operator deployment: `../aqp_platform/deployments/kubernetes/bots-operator/`.
- Helm charts: `../aqp_platform/deployments/helm/`.
- Argo Rollouts canary: `../aqp_platform/deployments/argocd/rollouts/`.
- HFT node tier: `../aqp_platform/deployments/kubernetes/hft-nodes/`.

## Validation

```bash
python -m pytest tests/bots
```

## ADRs

- [ADR 006 — QuantBot Operator Pattern](../aqp_docs/docs/architecture/decisions/006-quantbot-operator-pattern.md)
- [ADR 007 — QuantBot Latency Classes](../aqp_docs/docs/architecture/decisions/007-quantbot-latency-classes.md)
- [ADR 008 — Bot Event Sourcing](../aqp_docs/docs/architecture/decisions/008-quantbot-event-sourcing.md)
- [ADR 009 — RTS 6 / SEC 15c3-5 Conformance](../aqp_docs/docs/architecture/decisions/009-quantbot-rts6-conformance.md)
- [ADR 010 — Canary PnL Gates](../aqp_docs/docs/architecture/decisions/010-quantbot-canary-pnl-gates.md)
