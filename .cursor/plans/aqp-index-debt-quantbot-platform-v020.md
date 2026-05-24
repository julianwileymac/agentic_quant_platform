# aqp_index debt — QuantBot Platform v0.2.0

**Created:** 2026-05-24
**Owner:** aqp-index-curator (pending invocation)

## Why

Per `.cursor/rules/aqp-index-reflect.mdc`, every change touching the
qualifying surfaces below MUST either (a) invoke the
`aqp-index-curator` subagent and include its refresh in the diff, or
(b) drop a debt note that the curator can pick up on its next
scheduled pass. This work shipped via path (b).

## Qualifying surface that changed

The **QuantBot Platform v0.2.0 enterprise extension** (13 phases) added:

### New modules under `aqp_bots/`

- `aqp_bots/schemas/` — msgspec hot-path types (Tick / Quote / Bar /
  NewOrder / OrderAck / Fill / Position / ...).
- `aqp_bots/core/` — BotKernel + LifecycleFSM + Clock + ids +
  MessageBus + futures.
- `aqp_bots/adapters/` — MarketDataAdapter / ExecutionAdapter /
  ControlPlaneAdapter metaclass-driven Protocols + FIX/WS/REST/gRPC/
  onchain families + bridge adapters wrapping existing AQP brokerages.
- `aqp_bots/execution/` — Order FSM + OMS + EMS (TWAP/VWAP/POV/IS/
  Iceberg) + SOR + idempotency + reconcile.
- `aqp_bots/state/` — EventStore + SnapshotWriter + Projections +
  Replay.
- `aqp_bots/risk/` — PreTradeRiskEngine + RTS 6 Art. 15 policies +
  three-scope kill switch v2 + regulatory crosswalks + out-of-band
  FastAPI risk service.
- `aqp_bots/telemetry/` — OTel bridge + HFTSpanProcessor +
  microsecond Prometheus buckets + structlog + health probes.
- `aqp_bots/hft/` — Cython SPSC ring buffer + PTP clock + NUMA /
  HugePages / SR-IOV helpers + microsecond span integration + Rust
  escape hatch.
- `aqp_bots/operator/` — kopf handlers + 9 CRDs (Bot, Strategy,
  RiskPolicy, MarketDataFeed, ExecutionVenue, BacktestJob, BotFleet,
  CanaryRollout, KillSwitch) + Pydantic mirrors + CRD YAMLs +
  validating webhooks + finalizers + manifest renderer.

### New deployment artefacts under `aqp_platform/`

- `aqp_platform/deployments/kubernetes/bots-operator/` — operator
  Deployment, RBAC, webhook Service + ValidatingWebhookConfiguration,
  CRD-installer Job, PrometheusRule, ServiceMonitor.
- `aqp_platform/deployments/kubernetes/hft-nodes/` — kubelet config,
  Node Tuning Operator profile, PTP DaemonSet, SR-IOV policy,
  HugePages allocator.
- `aqp_platform/deployments/helm/{quantbot-platform,quantbot-bot,quantbot-fleet}/`.
- `aqp_platform/deployments/argocd/applicationsets/bot-fleet.yaml`.
- `aqp_platform/deployments/argocd/rollouts/` — canary template +
  3 AnalysisTemplates (pnl-vs-stable, reject-rate, p99-latency).

### Updated public surfaces

- `aqp_bots/spec.py` — added `Frequency`, `AssetClass`, `CapabilitySpec`,
  `DataLayerSpec`, `StrategyLayerSpec`, `RiskLayerSpec`,
  `ExecutionLayerSpec`, `StateLayerSpec`, `TelemetrySpec`, `LifecycleSpec`
  and integrated them into `BotSpec`.
- `aqp_bots/runtime.py` — added `BotRuntime.run_kernel()` (rule 14
  preserved).
- `aqp_bots/cli.py` — added `replay`, `conformance`, `stress`,
  `render-manifest`, `validate` subcommands.
- `aqp_bots/pyproject.toml` — bumped to 0.2.0; added optional extras
  `operator`, `hft`, `fix`, `onchain`, `otel`; added `aqp-bots-operator`
  console script.
- `aqp_bots/AGENTS.md` — hard rules for the new boundaries.
- `aqp_bots/README.md` — full v0.2.0 architecture.

### New ORM + migration

- `alembic/versions/0058_bot_event_sourcing.py` — `bot_events`
  (monthly-partitioned), `bot_orders`, `bot_fills`, `bot_snapshots`.
- `aqp/persistence/models_bots.py` — ORM mirrors of the four new tables.

### Extended FastAPI routes

- `aqp/api/routes/bots.py` — `/bots/{ref}/replay`, `/conformance`,
  `/stress`, `/risk/validation-report`, `/state/snapshot`,
  `/state/events`.

### New ADRs + runbooks under `aqp_docs/`

- `aqp_docs/architecture/decisions/006-quantbot-operator-pattern.md`
- `aqp_docs/architecture/decisions/007-quantbot-latency-classes.md`
- `aqp_docs/architecture/decisions/008-quantbot-event-sourcing.md`
- `aqp_docs/architecture/decisions/009-quantbot-rts6-conformance.md`
- `aqp_docs/architecture/decisions/010-quantbot-canary-pnl-gates.md`
- `aqp_docs/operations/hft-node-onboarding.md`
- `aqp_docs/operations/bot-canary-rollout-playbook.md`
- `aqp_docs/operations/rts6-validation-report-generation.md`
- `aqp_docs/operations/kill-switch-incident-response.md`
- `aqp_docs/bots.md` updated to link the above.

## Files in `aqp_index/` that need refreshing

- `aqp_index/architecture/aqp_bots.md` — refresh module map for v0.2.0.
- `aqp_index/architecture/operators.md` — add the QuantBot Operator.
- `aqp_index/code/token_index.md` — refresh signatures for new modules.
- `aqp_index/configurations/risk.md` — link the new RTS 6 / 15c3-5 mapping.
- `aqp_index/configurations/k8s.md` — link the HFT node tier + Argo
  Rollouts canary.
- `aqp_index/skills/` — add `quantbot-operator-skill.md`,
  `quantbot-risk-skill.md`, `quantbot-hft-skill.md`.
- `aqp_index/subagents/` — no new subagents needed.

## One-line summary for the curator

QuantBot Platform v0.2.0 = kopf operator + 9 CRDs + msgspec hot-path
schemas + metaclass-driven adapter Protocols + Order FSM + event
sourcing (Alembic 0058) + RTS 6 + 15c3-5 risk engine + Cython SPSC +
HFT node tier + Helm umbrella + Argo Rollouts canary. Strictly additive
to the existing `BotRuntime` / `bot_versions` path; AGENTS rules 14,
15, 28, 34, 45 preserved.
