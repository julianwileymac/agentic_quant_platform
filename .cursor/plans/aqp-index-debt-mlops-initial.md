# aqp_index debt — MLOps service (initial slice)

Per the always-on
[`aqp-index-reflect.mdc`](../../.cursor/rules/aqp-index-reflect.mdc)
rule: this commit touches qualifying surfaces and must either invoke
the [`aqp-index-curator`](../../.cursor/agents/aqp-index-curator.md)
subagent or open a debt note. This file is the deferred curator
record so the next pass can refresh `aqp_index/` deterministically.

## Surfaces touched (qualifying for reflection)

### Repo-root governance docs

- [AGENTS.md](../../AGENTS.md) — `aqp_models/` project-map row will
  need the new sub-package list (interfaces / handlers / adapters /
  skills / rules / productionize / ml_mcp). Add a row for `aqp-ml-mcp`
  alongside the existing `aqp-data-mcp` / `aqp-codebase-mcp` entries.
  Cross-references to the new Alembic 0081 tables and the
  `mlops_assistant` agent spec.

### `aqp_models/`

- `src/aqp_models/interfaces/` (new sub-package) — 7 modules:
  `__init__`, `base`, `predictor`, `forecaster`, `classifier`,
  `segmenter`, `analyzer`, `wrap`.
- `src/aqp_models/handlers/` (new sub-package) — 7 modules:
  `__init__`, `base`, `cache_handler`, `load_handler`,
  `save_handler`, `store_handler`, `productionize_handler`,
  `serve_handler`.
- `src/aqp_models/productionize/` (new sub-package) — 5 modules:
  `__init__`, `base`, `onnx_compile`, `tensorrt_compile`,
  `torchscript_compile`, `quantization`.
- `src/aqp_models/adapters/` (new sub-package) — 3 modules:
  `__init__`, `base`, `huggingface_adapter`, `torchhub_adapter`.
- `src/aqp_models/rules/` (new sub-package) — 4 modules:
  `__init__`, `base`, `ood_guard`, `circuit_breaker`.
- New top-level modules: `spec.py`, `runtime.py`, `registry.py`.
- New Celery task modules: `tasks/ml_pull_tasks.py`,
  `tasks/ml_serving_tasks.py`, `tasks/ml_productionize_tasks.py`,
  `tasks/ml_skill_tasks.py`.
- New FastAPI router: `api/routes/ml_skills.py`.
- Extended FastAPI router: `api/routes/ml.py` (new endpoints
  `/ml/models/pull`, `/ml/models/{id}/productionize`,
  `/ml/models/{id}/cache/warm`, `/ml/serving/sessions`,
  `/ml/serving/halt-all`).
- New YAML config dirs: `configs/skills/` (2 seed specs),
  `configs/rules/` (1 default OOD pack).
- New test dirs: `tests/interfaces/`, `tests/handlers/`,
  `tests/adapters/`, `tests/skills/`, `tests/rules/`.
- The [`aqp_models/AGENTS.md`](../../aqp_models/AGENTS.md)
  Where-Changes-Go section needs the new sub-package rows.

### `aqp/`

- `aqp/ml_mcp/` (new sub-package) — `__init__.py`, `server.py`.
- `aqp/data/mcp/tools/ml.py` (new) — 14 `data.ml.*` DataMCPTools.
- `aqp/data/mcp/tools/__init__.py` — added `ml` to the side-effect
  import list.
- `aqp/api/main.py` — mounted `_build_ml_mcp_router()` alongside the
  existing data / codebase MCP routers.
- `aqp/api/well_known.py` — added the
  `/.well-known/oauth-protected-resource/mcp/ml` route +
  `_ml_mcp_uri` / `_scopes_supported_ml` helpers.
- `aqp/api/mcp_audience.py` — added
  `get_ml_mcp_canonical_uri` helper + `__all__` entry.
- `aqp/persistence/models_mlops.py` (new) — 6 ORM classes mirroring
  the Alembic 0081 tables.
- `aqp/config/settings.py` — 9 new `ml_*` Settings fields +
  `mcp_ml_canonical_uri` + `mcp_ml_url`.
- `aqp/config/topology_fallback.py` — new `mcp_ml_url` mapping.
- `aqp/tasks/celery_app.py` — included the four new task modules +
  matching `task_routes` entries on the `ml` queue.

### `configs/agents/`

- `configs/agents/mlops_assistant.yaml` (new) — `AgentSpec` for the
  report's autonomous MLOps researcher. Only references registered
  `data.ml.*` / `data.discovery.*` / `data.catalog.*` tools.

### `aqp_platform/configs/deployment/`

- `topology.yaml` — new `aqp-ml-mcp` service entry mapping to the
  in-pod FastAPI router (port 8000, `/mcp/ml`).

### `alembic/versions/`

- `0081_mlops_skills_and_artifacts.py` (new) — six new tables
  (`ml_skills`, `ml_skill_versions`, `ml_skill_runs`,
  `ml_compiled_artifacts`, `ml_cache_entries`, `ml_serving_sessions`,
  `ml_ood_violations`). Down-revision: `0080_team_airbyte_workspaces`.
  Hash logged in `alembic/versions/.hashes.lock`.

### `aqp_client/`

- New routes: `src/routes/ml/{skills,serving,pull}/page.tsx`.
- New components: `src/components/ml/{MlSkillsPage,MlServingPage,MlPullPage}.tsx`.
- Extended `src/lib/api/ml.ts` — added 7 new wrapper methods
  (`pull`, `productionize`, `cacheWarm`, `servingSessions`,
  `haltAllServing`, `skills`, `describeSkill`, `runSkill`).
- Updated `src/components/common/KillSwitch.tsx` — appended
  `/ml/serving/halt-all` to `HALT_ENDPOINTS`.

### Tests

- `aqp_models/tests/{interfaces,handlers,adapters,skills,rules}/` —
  hermetic unit tests for the new subpackages.
- `tests/data/mcp/test_ml_tools.py` — DataMCP catalog discovery
  tests.
- `tests/api/test_mcp_ml_rfc8707.py` — RFC 9728 + 8707 smoke tests.
- `tests/api/test_ml_serving_halt.py` — kill-switch fan-out coverage.

## What the curator pass should produce

1. `aqp_index/code-index/modules.md` — append rows for the new
   `aqp_models/{interfaces,handlers,adapters,rules,productionize}/`
   subpackages + the new `aqp/ml_mcp/` package + new
   `aqp/data/mcp/tools/ml.py` + `aqp/persistence/models_mlops.py`.
2. `aqp_index/architecture/boundaries.md` — extend the `aqp_models/`
   boundary description with the new agentic plumbing layer.
3. `aqp_index/skills/aqp-mlops-skill.md` (new) — describe the
   `MLSkillSpec` + `MLSkillRuntime` pattern for future automated
   skill authoring.
4. `aqp_index/code-index/configs.md` — list the two new
   `aqp_models/configs/skills/` YAMLs + the OOD rule pack.
5. `aqp_index/architecture/migrations.md` — log Alembic 0081.

## Why this is a debt note rather than a curator invocation

The slice spans 60+ new files across five top-level boundaries.
Running the curator inside the same window the implementation
landed risks churning `aqp_index/` against a still-settling code
state. A follow-up commit drives the curator over the merged tree
in one deterministic pass.
