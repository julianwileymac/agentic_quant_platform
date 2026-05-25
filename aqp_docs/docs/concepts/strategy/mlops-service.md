---
title: MLOps service (initial slice)
last_reviewed: 2026-05-25
---

# MLOps service inside `aqp_models/`

This page documents the initial MLOps service shipped as additive
extensions to the established `aqp_models/` boundary. The service
provides the agentic plumbing the two MLOps reports asked for — a
polymorphic agent-facing interface layer, MLOps lifecycle handlers,
external-registry adapters, hash-locked skills, OOD safety rules, a
dedicated MCP server, and the matching REST + Celery + frontend
surfaces — all on top of the existing models / predictors / serving
infrastructure.

## What's new

### `aqp_models/src/aqp_models/interfaces/`

Five agent-facing polymorphic ABCs that wrap any concrete model in a
stable contract:

| Interface | Method | Application |
| --- | --- | --- |
| `Predictor` | `predict(features)` | Point-in-time value estimation |
| `Forecaster` | `forecast(history, horizon)` | Multi-step temporal projection |
| `Classifier` | `classify(data)` | Discrete probability distribution |
| `Segmenter` | `segment(series)` | Structural-break detection |
| `Analyzer` | `analyze(unstructured)` | NLP / sentiment scoring |

All register under `kind="interface"` in `aqp.core.registry`. Agents
program against `Predictor.predict` regardless of whether XGBoost,
LSTM, or HuggingFace pipelines back the call.

### `aqp_models/src/aqp_models/handlers/`

Six MLOps lifecycle handler classes:

| Handler | Purpose |
| --- | --- |
| `CacheHandler` | LRU + safetensors-first model cache (budgets in `settings.ml_cache_*`) |
| `LoadHandler` | Cryptographic verification + safetensors-preferred deserialisation |
| `SaveHandler` | torch state_dict → `.safetensors` with SHA-256 sidecar |
| `StoreHandler` | Object-store upload + lineage metadata |
| `ProductionizeHandler` | Drive the `productionize/` compiler pipeline |
| `ServeHandler` | Continuous-batching queue with kill-switch fan-out |

All inherit `MLOpsHandler` so every lifecycle operation runs the same
`policy_check` + lineage emission contract (`LineageBus`).

### `aqp_models/src/aqp_models/productionize/`

Four compiler classes:

| Compiler | Output | Optional dep |
| --- | --- | --- |
| `OnnxCompiler` | `.onnx` | `torch.onnx` |
| `TensorRTCompiler` | `.engine` | `tensorrt` (Linux GPU only) |
| `TorchScriptCompiler` | `.pt` (trace/script) | `torch` |
| `QuantizationCompiler` | `.pt` (INT8 / FP16) | `torch` |

Each registers via `@register_compiler("alias")` and emits a
`CompiledArtifact` with SHA-256 + size + kwargs into
`ml_compiled_artifacts`.

### `aqp_models/src/aqp_models/adapters/`

External-registry pullers protecting the supply chain:

| Adapter | Notes |
| --- | --- |
| `HuggingFaceAdapter` | Routes downloads through the local cache volume; resolves HF tokens via `CredentialResolver` (`CredentialKey("huggingface", "api_token")`). Honours `settings.ml_hf_hub_offline`. |
| `TorchHubAdapter` | Refuses every name not on `DEFAULT_ALLOWLIST` ∪ the operator allow-list at `CredentialKey("torchhub", "allowlist")`. Verifies SHA-256 before caching. |

### `aqp_models/src/aqp_models/spec.py` + `runtime.py` + `registry.py`

Hash-locked **MLSkillSpec** + **MLSkillRuntime** mirroring the
existing `AgentSpec`/`BotSpec`/`RLExperimentSpec`/`AnalysisSpec`
runtime pattern. New Alembic 0081 tables:

- `ml_skills` + `ml_skill_versions` (hash-locked snapshots)
- `ml_skill_runs` (run ledger with `experiment_id` + `test_id` FKs, AGENTS rule 34)

Seed skill YAMLs ship under `aqp_models/configs/skills/`:

- `regime_aware_alpha.yaml` — Classifier → Predictor (regime-specialised)
- `multi_horizon_forecast.yaml` — Forecaster + Analyzer (sentiment overlay)

### `aqp_models/src/aqp_models/rules/`

Inference-time OOD safety rules driven by a metaclass-driven
`RuleRegistry`:

- `OODGuard` — z-score threshold check.
- `RangeGuard` — absolute min/max window check.
- `TensorShapeGuard` — input-shape mismatch check.
- `CircuitBreaker` — rolling-window failure tracker that trips at
  `max_failures` per `window_seconds`.

Rule packs live under `aqp_models/configs/rules/`; the default is
`ood_default.yaml`.

### `aqp/data/mcp/tools/ml.py`

Fourteen `data.ml.*` DataMCP tools — the canonical Hard Rule 22 path
agents use to drive the entire MLOps surface (predict, forecast,
classify, segment, analyze, pull, compile, list, run skills, halt
serving). Each tool registers via `@register_data_mcp_tool` so both
transports — the in-process bridge and the FastAPI
router/stdio binary — pick it up.

### `aqp/ml_mcp/` + `aqp-ml-mcp` binary

A dedicated MCP server publishing the same `data.ml.*` slice under
its own canonical URI (`settings.mcp_ml_canonical_uri`). Tokens
minted for the MLOps audience cannot be replayed against the data
MCP and vice versa (RFC 8707, Hard Rule 49). The RFC 9728 metadata
document lives at `/.well-known/oauth-protected-resource/mcp/ml`.

### REST + Celery

New routes under the existing `/ml/*` router plus a fresh
`/ml/skills/*` router. Long-running ops dispatch to four new Celery
modules: `ml_pull_tasks`, `ml_serving_tasks`,
`ml_productionize_tasks`, `ml_skill_tasks`. All emit progress via
`_progress.emit` (Hard Rule 4).

### Frontend (Vite)

Three new routes under `aqp_client/src/routes/ml/`:

- `/ml/skills` — registry browser + invocation form.
- `/ml/serving` — live continuous-batching session monitor with
  per-session halt button.
- `/ml/pull` — HuggingFace/TorchHub model puller.

`KillSwitch.tsx` fans out to `POST /ml/serving/halt-all` alongside
the existing halt endpoints (Hard Rule 2 in `frontend.mdc`).

### Identity + topology

- `aqp.config.settings` gains nine new `ml_*` knobs (cache budgets,
  serving defaults, OOD threshold, offline toggles, MCP canonical URI
  + URL).
- `aqp_platform/configs/deployment/topology.yaml` gains an
  `aqp-ml-mcp` service entry (Hard Rule 47).
- `aqp/config/topology_fallback.py` maps `mcp_ml_url` →
  `aqp-ml-mcp.http`.

## Agent usage

The seed `mlops_assistant` AgentSpec at
`configs/agents/mlops_assistant.yaml` drives the MLOps surface
exclusively through the `data.ml.*` tools. Operators invoke it the
same way as any other AgentSpec — `AgentRuntime.run(...)` (never call
`router_complete` directly per Hard Rule 12).

## Validation

```bash
# Source compile check:
python -m py_compile aqp_models/src/aqp_models/{interfaces,handlers,adapters,rules,productionize,tasks}/**/*.py

# New migration is hashed into the lock file:
python scripts/ci/check_migration_immutability.py

# DataMCP catalog discovery:
curl http://localhost:8000/mcp/data/tools | jq '.tools[] | select(.name | startswith("data.ml."))'

# MLOps MCP discovery:
curl http://localhost:8000/.well-known/oauth-protected-resource/mcp/ml
```

## What is explicitly out of scope

- Mutating an existing migration. The 0081 migration is immutable
  once shipped (Hard Rule 6); future schema changes land in 0082+.
- Streamlit / Solara surfaces. The legacy stack is rollback-only.
- Free-text URN input. Every entity selection uses `EntityPicker`
  (Hard Rule 29).
