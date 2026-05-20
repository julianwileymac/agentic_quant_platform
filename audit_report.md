> Archived context note: point-in-time audit output retained for traceability.  
> Use current rules and runbooks for active decisions. See
> `docs/archive/README.md`.

# AQP Metadata & Lineage Consolidation Hard-Rules Audit

Scope audited: metadata/aspect refactor files listed in the request (plus directly adjacent migration/agent boundary checks needed for AGENTS hard-rule validation).  
Mode: read-only audit (no code changes), targeted grep/read validation.

## Rule 6 (immutable migrations): **FAIL**

### Evidence
- **Shipped migration edited**: `alembic/versions/0046_workflow_versioning.py` was modified after commit.  
  - Diff evidence (`git diff ccd02e7..HEAD -- alembic/versions/0046_workflow_versioning.py`):
    - `alembic/versions/0046_workflow_versioning.py:184`
      - `["experiment_id"], ["aqp_experiments.id"], ondelete="SET NULL"` (was `experiments.id`)
    - `alembic/versions/0046_workflow_versioning.py:187`
      - `["test_id"], ["aqp_tests.id"], ondelete="SET NULL"` (was `tests.id`)
- **Unexpected parallel 0049 migration files present**:
  - `alembic/versions/0049_paper_baseline_aspects.py:20` -> `down_revision = "0048_metadata_aspects"`
  - `alembic/versions/0049_paper_metadata_seed_aspects.py:21` -> `down_revision = "0048_metadata_aspects"`
  - This creates two `0049`-level descendants from `0048` in-tree.
- **Requested chain segments do point correctly**:
  - `alembic/versions/0048_metadata_aspects.py:23` -> `down_revision = "0047_data_fabric_foundation"`
  - `alembic/versions/0049_paper_metadata_seed_aspects.py:21` -> `down_revision = "0048_metadata_aspects"`

## Rule 7 (settings-only env access): **PASS (in scoped new code)**

### Evidence
- No direct `os.environ`, `os.getenv`, or `os.environ.get` found in the targeted metadata/aspect refactor modules (metadata package, new MCP tools, DataHub aspect files, trading gate files, aspect API route, and 0048/0049 metadata migrations).
- `aqp/config/settings.py` contains env reads by design (centralized settings source of truth), which is compliant.

### Violations in scoped new code
- None found.

## Rule 22 (DataMCPTool boundary): **PASS (no new violations in refactor scope)**

### Evidence
- `git diff --name-only ccd02e7..HEAD -- aqp/agents` returned no changed files for this refactor window.
- No new `aqp/agents/*` modules in the audited scope introduced `from aqp.persistence.models...` imports.

### Violations in scoped new code
- None found.

## Rule 26 (CredentialResolver): **FAIL**

### Violations
- `aqp/data/datahub/aspect_puller.py:228`
  - `token=(settings.datahub_token or None),`
  - Direct service token access outside `aqp/credentials/`; should resolve through `CredentialResolver`.

## Rule 29 (BaseDataset + EntityPicker): **FAIL**

### Violations
- `aqp_client/src/routes/metadata/aspects/page.tsx:183`
  - Free-text URN field:
  - `<Input ... placeholder="urn:aqp:dataset:prod:aqp_silver_alpha_vantage.daily_bars" ... />`
  - This is an entity-selection input path implemented as free text instead of a cache-backed picker.
- `aqp_client/src/routes/metadata/aspects/page.tsx:135`
  - Inline TODO confirms missing picker integration:
  - `replace with EntityPicker.`

## Rule 33-34 (tenancy + experiment_id): **FAIL**

### 33 ownership/tenancy evidence
- **ORM mixins present**:
  - `aqp/persistence/models_aspects.py:27` -> `class MetadataEntity(Base, ProjectScopedMixin):`
  - `aqp/persistence/models_aspects.py:38` -> `class EntityAspect(Base, ProjectScopedMixin):`
- **Workspace tenancy filter implemented in primary reads**:
  - `aqp/data/mcp/tools/aspects.py:33-37` (`workspace_id == ctx.workspace_id OR workspace_id IS NULL`)
  - `aqp/data/mcp/tools/aspects.py:762` history query applies `_workspace_scope_clause(ctx)`
  - `aqp/data/mcp/tools/datahub.py:136-144` scoped EntityAspect read applies `(workspace_id == ctx.workspace_id OR IS NULL)`
- **Violation (missing tenancy filter on an EntityAspect read)**:
  - `aqp/data/mcp/tools/aspects.py:670-676`
  - Query reads latest `EntityAspect` by URN/aspect without applying `_workspace_scope_clause(ctx)` (or equivalent workspace predicate).

### 34 experiment_id evidence
- No new run table added by metadata migrations (`0048`, `0049_*` are aspect/entity focused).
- `MlTestResult` is modeled and persisted as an **aspect**, not a run row:
  - `aqp/metadata/openmetadata/models_ml.py:216` -> `class MlTestResult(...)`
  - `aqp/tasks/ml_test_tasks.py:224` -> `write_aspect(session, model_urn, "mlTestResult", payload)`
- Conclusion: no `experiment_id` requirement triggered for these aspect records.

## Style checks (`__future__`, print, Pydantic V2, logging): **PASS (in scoped new code)**

### Evidence
- `from __future__ import annotations` present across new metadata/aspect Python modules (including `aqp/metadata/*`, `aqp/persistence/models_aspects.py`, `aqp/data/datahub/aspect_*`, `aqp/data/mcp/tools/aspects.py`, `aqp/data/mcp/tools/namespace_policy.py`, `aqp/rag/document_aspects.py`, `aqp/api/routes/metadata_aspects.py`, `aqp/trading/metadata_gate.py`, `alembic/versions/0048*`, `alembic/versions/0049*`).
- No `print()` function usage found in scoped new Python files (only `Console().print(...)` in `aqp/metadata/schema_export.py`, which is not the built-in `print()` call).
- No `.dict()` / `.parse_obj()` / `pydantic.v1` usage found in scoped new Python files.
- Modules using `import logging` in scoped files define `logger = logging.getLogger(__name__)`.

### Style violations in scoped new code
- None found.

## Aggregate verdict: **RED (blocking violations)**

Blocking hard-rule findings:
1. Rule 6: shipped migration `0046_workflow_versioning.py` edited post-commit.
2. Rule 6: concurrent `0049_*` descendants from `0048` present (`baseline` + `metadata_seed`).
3. Rule 26: direct `settings.datahub_token` access in `aqp/data/datahub/aspect_puller.py:228`.
4. Rule 29: free-text URN entity selection in `aqp_client/src/routes/metadata/aspects/page.tsx:183`.
5. Rule 33: unscoped `EntityAspect` read in `aqp/data/mcp/tools/aspects.py:670-676`.

---

## Out-of-scope / adjacent pre-existing findings (informational)

- **Rule 22 boundary (existing agent modules):** direct persistence-model imports exist under `aqp/agents/*` (examples: `aqp/agents/runtime.py:232`, `aqp/agents/analysis/reflector.py:43`, `aqp/agents/strategy_memory.py:30`).
- **Rule 26 credential pattern (existing):** `aqp/data/datahub/client.py:35` uses `settings.datahub_token` directly.
- **Rule 7 env access (existing/non-targeted areas):**
  - `aqp/api/routes/sources.py:360`, `aqp/api/routes/sources.py:628`
  - `alembic/versions/0051_seed_wiley_tech.py` (multiple `os.environ.get(...)` calls)
- **Pydantic V2 style (existing/non-targeted):**
  - `aqp/data/iceberg_catalog.py:1292` -> `.dict()`
  - `aqp/data/airbyte/embedded.py:142` -> `.dict()`
