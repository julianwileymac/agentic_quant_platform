# Runtimes

> Last refreshed: 2026-05-23 (seed).

AQP uses a spec + runtime pattern for every long-running operation.
Specs are hash-locked, runtimes are the single sanctioned executors.

| Runtime | Spec | Canonical doc | Hard rules |
| --- | --- | --- | --- |
| `AgentRuntime` | `AgentSpec` | [../../aqp_docs/agents.md](../../aqp_docs/agents.md) | AGENTS rules 12-13 |
| `BotRuntime` | `BotSpec` | [../../aqp_docs/bots.md](../../aqp_docs/bots.md) | AGENTS rules 14-15 |
| `RLRuntime` | `RLExperimentSpec` | [../../aqp_docs/rl-framework.md](../../aqp_docs/rl-framework.md) | AGENTS rules 16-20, 36-38 |
| `AnalysisRuntime` | `AnalysisSpec` | [../../aqp_docs/analysis-framework.md](../../aqp_docs/analysis-framework.md) | AGENTS rules 23-25 |
| `WorkflowRuntime` | `WorkflowSpec` | [../../aqp_docs/workflow-studio.md](../../aqp_docs/workflow-studio.md) | AGENTS rules 40-41 |
| `TerraformRuntime` | `TerraformStackSpec` | [../../aqp_docs/terraform-control-plane.md](../../aqp_docs/terraform-control-plane.md) | AGENTS rules 42-43 |
| `WorkloadRuntime` | `InfrastructureProvider` | [../../aqp_docs/management-engine.md](../../aqp_docs/management-engine.md) | AGENTS rule 45 |

All version rows (`*_spec_versions`) are immutable. Resnapshotting a
changed spec creates a new row; old rows stay for replay / audit.
