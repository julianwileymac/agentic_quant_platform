# Runtimes

> Last refreshed: 2026-05-25 by aqp-index-curator (trigger: enterprise
> docs migration Phase 0 — every canonical-doc pointer rewritten from
> the legacy `aqp_docs/<slug>.md` shape to the Docusaurus
> `aqp_docs/docs/<category>/<slug>.md` shape per `CONCEPT_MAPPING` in
> `aqp_docs/scripts/migrate-content.py`).

AQP uses a spec + runtime pattern for every long-running operation.
Specs are hash-locked, runtimes are the single sanctioned executors.

| Runtime | Spec | Canonical doc | Hard rules |
| --- | --- | --- | --- |
| `AgentRuntime` | `AgentSpec` | [../../aqp_docs/docs/concepts/agentic/agents.md](../../aqp_docs/docs/concepts/agentic/agents.md) | AGENTS rules 12-13 |
| `BotRuntime` | `BotSpec` | [../../aqp_docs/docs/concepts/agentic/bots.md](../../aqp_docs/docs/concepts/agentic/bots.md) | AGENTS rules 14-15 |
| `RLRuntime` | `RLExperimentSpec` | [../../aqp_docs/docs/concepts/rl/rl-framework.md](../../aqp_docs/docs/concepts/rl/rl-framework.md) | AGENTS rules 16-20, 36-38 |
| `AnalysisRuntime` | `AnalysisSpec` | [../../aqp_docs/docs/concepts/strategy/analysis-framework.md](../../aqp_docs/docs/concepts/strategy/analysis-framework.md) | AGENTS rules 23-25 |
| `WorkflowRuntime` | `WorkflowSpec` | [../../aqp_docs/docs/concepts/agentic/workflow-studio.md](../../aqp_docs/docs/concepts/agentic/workflow-studio.md) | AGENTS rules 40-41 |
| `TerraformRuntime` | `TerraformStackSpec` | [../../aqp_docs/docs/concepts/infrastructure/terraform-control-plane.md](../../aqp_docs/docs/concepts/infrastructure/terraform-control-plane.md) | AGENTS rules 42-43 |
| `WorkloadRuntime` | `InfrastructureProvider` | [../../aqp_docs/docs/concepts/identity/management-engine.md](../../aqp_docs/docs/concepts/identity/management-engine.md) | AGENTS rule 45 |

All version rows (`*_spec_versions`) are immutable. Resnapshotting a
changed spec creates a new row; old rows stay for replay / audit.
