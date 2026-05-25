# AQP Restructuring & Refactoring Plan

> Calibrated to the **current** repo state (Alembic head `0080`, 55
> hard rules, 14 subprojects mid-extraction). Many audit findings have
> already been partially remediated; the underlying *class* of
> vulnerability survives because no CI gates prevent regression. The
> blueprint's cell pattern is directionally correct but must be
> layered on top of the existing `TenancyStrategy` primitives
> (Alembic `0063`/`0064`), not stamped over them.

---

## How to read this plan

- **Categories**: every action is tagged `[FIX]`, `[ENHANCE]`,
  `[ADD]`, or `[REMOVE]`.
- **Anchors**: every action references the AGENTS hard rule it
  enforces (e.g. `[Rule 6]`) and a citation-format file/line.
- **Sequencing**: phases are time-boxed but most can proceed in
  parallel. Hard dependencies are explicit.
- **Audit traceability**: Section 1 maps each May-2026 audit finding
  to the *current* state of the offending file. Anything left
  **Open** is re-routed into Phase 0; **Closed** items still get a CI
  gate so they cannot regress.
- **Risk discipline**: every removal has a deprecation shim path;
  every add has a feature flag.

---

## 1. Audit reality check (May 2026 → today)

| Audit finding | Current file / line | State | Gating |
| --- | --- | --- | --- |
| **Rule 6** — `0046_workflow_versioning.py` mutated post-commit | `alembic/versions/0046_workflow_versioning.py:175-198` retains the post-commit edit to `aqp_experiments.id` / `aqp_tests.id` with an apologetic comment block; docstring at `:17` still asserts immutability | **Open — text-of-the-rule is broken** | No `.hashes.lock`, no CI gate |
| **Rule 6** — bifurcated `0049` descendants | The second file was renumbered to `alembic/versions/0053_paper_metadata_seed_aspects.py` | **Closed in tree** | No topology lint |
| **Rule 26** — direct `settings.datahub_token` reads | `aqp/data/datahub/aspect_puller.py:225-234` unchanged; comment now says "grandfathered". Same anti-pattern at `aqp/data/datahub/client.py:35`, `aqp/data/sources/alpha_vantage/datahub.py`, `aqp/tasks/visualization_tasks.py` | **Open — wider than audit reported** | No lint |
| **Rule 29** — free-text URN input | Moved to `aqp_client/src/routes/metadata/aspects/page.tsx:182-200`. Hardened to a `<datalist>` combobox but still a free-text `<Input>`. Two TODOs call for the `EntityPicker` swap once `metadata_entity_types` + `metadata_entity_urns` ship in `CACHE_CATEGORIES` | **Open — partial** | No lint |
| **Rule 33** — unscoped EntityAspect read at `aspects.py:670-676` | `aqp/data/mcp/tools/aspects.py:771-777` now applies `_workspace_scope_clause(ctx)` | **Closed** | No regression test |
| **Style** — Pydantic V1 `.dict()` / `.parse_obj()` | Need re-grep; CI has no `pydantic-v1-call` rule | **Unknown** | No lint |
| **Style** — legacy `print()` outside scoped modules | No CI rule beyond manual review | **Unknown** | No lint |
| **Boundary** — `aqp/agents/runtime.py:232` direct ORM import | `aqp/agents/runtime.py:341-405` still imports `AgentRunV2` / `AgentRunStep` directly. Same anti-pattern in `aqp/agents/strategy_memory.py:30`, `aqp/agents/analysis/reflector.py`, and 12 other files (42 hits across 15 files) | **Open — wider than audit reported** | Rule 22 unenforced by lint |

**Net**: 5 audit findings open, 1 closed-in-tree but ungated, 2
unknown-but-ungated. The single highest-leverage remediation is the
**CI gate layer**, not the line edits.

---

## 2. Current architecture snapshot

### 2.1 Subproject inventory and extraction state

| Subproject | Status | Strict `aqp.*` boundary? | Test coverage in CI? | AGENTS.md? |
| --- | --- | --- | --- | --- |
| `aqp/` (legacy monolith) | Active | n/a | Partial (no CI step running `tests/`) | Master AGENTS.md |
| `aqp_platform_core/` | Active | Enforced (ADR 005) | Yes (`test-platform-core` job) | Yes |
| `aqp_control_plane/` | Active | Enforced via grep gate at `.github/workflows/ci.yml:62-69` | Yes (`test-control-plane` job) | Yes |
| `aqp_admin/` | Active | Documented (`never import aqp.*`) — **no CI gate** | No CI job | Yes |
| `aqp_ui/` | Active | Documented — **no CI gate** | No CI job | Yes |
| `aqp_client/` | Active (Vite 7 + React 19) | Documented | npm audit + frontend tests `aqp-ui.yml` | Yes |
| `aqp_cli/` | Active | Documented | No CI job | Yes |
| `aqp_ide/` | Active (white-labeled Theia) | Documented | No CI job | Yes |
| `aqp_ingest/` | Active | Documented | No CI job | Yes |
| `aqp_kernels/` | Active | Documented | No CI job | Yes (assumed) |
| `aqp_ratelimit/` | Active | Documented | No CI job | Yes (assumed) |
| `aqp_rl/` | Active | Documented; `aqp/rl/` is a deprecation shim | No CI job | Yes |
| `aqp_models/` | Active | Documented; `aqp/ml/` is a deprecation shim | No CI job | Yes |
| `aqp_bots/` | Active | Documented | No CI job | Yes |
| `aqp_platform/` | Active (IaC + manifests + Dockerfiles) | Documented | Partial (`security-scan.yml` Trivy) | Yes |
| `aqp_index/` | Curator-only | n/a | n/a | Yes |
| `aqp_docs/` | Active | n/a | `docs-ci.yml` | Yes |
| `aqp_snippets/` | Reference-only | n/a | n/a | Yes |
| `webui/` (legacy Next.js) | Rollback-only | n/a | `webui.yml` | n/a |

**Critical CI gap**: only **2 of 14** active subprojects run unit
tests in CI. The boundary gate at `.github/workflows/ci.yml:62-69`
exists only for `aqp_control_plane`. Everything else relies on
voluntary AGENTS.md compliance.

### 2.2 Hard rules with no enforcement

| Rule | Subject | Why ungated |
| --- | --- | --- |
| **6** | Migrations immutable; no bifurcation | No `.hashes.lock`, no `alembic check` job |
| **7** | `settings`-only env access | No `os.environ`/`os.getenv` AST lint |
| **9** | `logging.getLogger(__name__)` not `print` | No `print` lint outside `scripts/` |
| **22** | Agents must not import ORM models | No `aqp.persistence` import lint inside `aqp/agents/**` |
| **26** | All cross-service credentials via `CredentialResolver` | No `settings.*_token` AST lint |
| **29** | Entity inputs via `EntityPicker` | No frontend lint for free-text URN inputs |
| **49** | MCP tokens carry `aud` | Only tested at runtime; no static check on new tools |
| **51** | Tenancy via `TenancyStrategy` | No lint for `engine.connect()` outside the strategy layer |
| **52** | Step-up MFA on listed routes | No static check that listed routes have `Depends(require_step_up(...))` |
| **54** | Delegated agent tokens via `TokenExchangeBroker` | No lint for direct MCP HTTP calls bypassing the broker |
| **55** | BYOK broker credentials via `BrokerCredentialStore` | No lint for direct `settings.alpaca_*` / `settings.ibkr_*` reads |

The single most impactful work in this plan is converting these
documented rules into mechanically-checked gates.

### 2.3 Strategic primitives already in place

The blueprint treats these as net-new. They already exist:

- **Tenancy tiers** = `SharedSchemaRLSStrategy`,
  `SchemaPerTenantStrategy`, `DatabasePerEnterpriseStrategy`,
  `HybridStrategy` (Rule 51, Alembic `0063`/`0064`). One-to-one map
  to blueprint's `shared-std` / `shared-prem` / `silo-reg` / hybrid.
- **Hash-locked spec versions** (Rules 13, 15, 17, 24, 41, 43) for
  Agents, Bots, RL, Analysis, Workflows, Terraform — exactly the
  "immutable, content-addressed, deterministic-replay" pattern the
  blueprint's audit lake requires.
- **Credential resolution chain** at `aqp/credentials/resolver.py`
  with envelope encryption via `aqp/credentials/vault_transit.py`
  (Rules 26, 50, 55) — already layered:
  `BrokerCredentialStore` (4) > `UserOAuthTokenStore` (5) >
  `M2MTokenIssuer` (10).
- **MCP audience binding** (Rule 49, RFC 9728+8707) and
  **token exchange** (Rule 54, RFC 8693).
- **Step-up MFA** (Rule 52, RFC 9470) on every destructive route.
- **Audit-log hash chain** (Alembic `0079`) and **OpenLineage
  outbox** (Alembic `0060`, `0061`).
- **Topology service** (Rule 47) at `aqp/config/topology_fallback.py`
  — the cell-router registry can extend this.

### 2.4 Strategic primitives that are net-new

Nothing in the repo currently provides:

- Service mesh (Linkerd / Istio / Cilium)
- SPIFFE / SPIRE workload identity
- Cosign / Sigstore image signing
- Syft SBOM attestation
- Kyverno admission policies / signature verification
- Pod Security Standards `restricted` enforcement
- gVisor / Kata / Firecracker sandbox for agent-generated code
- Cedar policy engine
- Biscuit capability tokens
- Per-tenant MCP server isolation (single shared MCP today)
- Per-cell PostgreSQL deployment (single Postgres today)
- Per-cell object storage (single Iceberg warehouse)
- KServe / vLLM multi-tenant inference (shared LLM gateway only)
- Envoy cell router (Python FastAPI proxy in `aqp_client` today)

These are the additions in Sections 5–11.

---

## 3. Phase 0 — Audit closure (Weeks 1–2, blocking)

**Goal**: every open audit finding gets a concrete PR with a
regression test and a CI gate that prevents recurrence. No exceptions
land in `main` without the gate.

### 3.1 `[FIX]` Rule 6 — migration immutability

The defensive comment block at
`alembic/versions/0046_workflow_versioning.py:175-198` is the wrong
shape. "Never-successfully-applied" is not a defensible exception when
the source of truth is the file in git, not the deployed state.

**Action**:

1. Compute the SHA-256 of every migration as of today; write to
   `alembic/versions/.hashes.lock` (JSON, sorted). One-shot
   operation that accepts the current state (including patched
   `0046`) as the new baseline.
2. Land `scripts/ci/check_migration_immutability.py` that re-hashes
   every file each PR and fails on drift. New migrations are
   auto-appended to the lock file when they appear; existing entries
   may not change.
3. Land `scripts/ci/check_migration_chain.py` — verifies exactly one
   head, no orphan parents, no two non-merge revisions share a
   `down_revision`. Uses `alembic.script.ScriptDirectory`.
4. Pre-commit hook + CI job in `.github/workflows/ci.yml`.
5. Amend AGENTS Rule 6 documentation with the operational procedure
   for "I need to fix a migration before it has been applied
   anywhere" — the right answer is *still* a new migration, plus an
   `alembic_version` repair script when needed, never an in-place
   edit.

**Why hash-from-current-state and not a blueprint-style compensating
migration**: the blueprint proposes `0050_fix_0048.py` /
`0051_fix_0049.py`, but those revision IDs are already taken
(`0050_terraform_iac_plus_entra.py`, `0051_seed_wiley_tech.py`).
Re-numbering forward (`0081_fix_0046.py`) is also wrong because the
schema state on every deployed environment is already what the
patched `0046` produces — additional DDL would either be a no-op
(`if not exists` everywhere) or diverge fresh-bootstrap from
upgrade. The honest fix is: accept the current state, lock it,
prevent recurrence.

**Regression test**: `tests/ci/test_migration_immutability.py`
writes a known-state lock, mutates a copy of a migration, asserts
script exits non-zero.

### 3.2 `[FIX]` Rule 26 — eradicate `settings.*_token` direct reads

Targets (scope wider than the audit):

| File | Refactor target |
| --- | --- |
| `aqp/data/datahub/client.py:35` | Constructor token fallback → `CredentialResolver.resolve(scope=CredentialScope(resource="datahub", ...))` |
| `aqp/data/datahub/aspect_puller.py:230` | Same |
| `aqp/data/sources/alpha_vantage/datahub.py` | Same |
| `aqp/tasks/visualization_tasks.py` | Same |
| `aqp_platform/rollback/rpi_k8s_sdk/src/rpi_k8s_sdk/datahub.py` | Rollback-only — wrap in `if AQP_CONTROL_PLANE_LEGACY_FALLBACK` guard mirroring `ClusterMgmtClient` (Rule 47) |

**Action**:

1. New `DataHubCredentialStore` under `aqp/credentials/stores/` that
   resolves `datahub_token` / `datahub_gms_url` / `datahub_env` from
   the configured priority chain.
2. Refactor each call site to obtain credentials through
   `CredentialResolver.current().resolve(...)`.
3. Rename `Settings.datahub_token` to `_bootstrap_datahub_token`
   (underscore-private). Any external read becomes the lint failure.
4. New CI lint `scripts/ci/check_credential_resolver.py` (AST scan)
   bans `settings.*_token` / `_secret` / `_credential` / `_api_key`
   reads outside `aqp/credentials/` and `aqp/config/settings.py`.
5. Wire into `.github/workflows/ci.yml` `lint` job.
6. Regression test `tests/ci/test_credential_resolver_lint.py` —
   fake module with `settings.foo_token` must fail.

### 3.3 `[FIX]` Rule 29 — EntityPicker for URN inputs

**Action**:

1. Add `metadata_entity_types` and `metadata_entity_urns` to
   `aqp/cache/keys.py::CACHE_CATEGORIES`.
2. Add populators in `aqp/cache/prefetch.py::MetadataPrefetcher`.
   The populator for `metadata_entity_urns` queries `MetadataEntity`
   scoped to `RequestContext.workspace_id` via the active
   `TenancyStrategy` (Rule 51) — the tenant boundary is **baked into
   the cache**, so a workspace's UI can only see its own URNs.
3. Replace the free-text `<Input>` at
   `aqp_client/src/routes/metadata/aspects/page.tsx:193-200` and the
   `<select>` at `:136-152` with `<EntityPicker
   kind="metadata_entity_urns" />` and
   `<EntityPicker kind="metadata_entity_types" />`.
4. Backend defense-in-depth: every `metadata-aspects` route asserts
   `MetadataEntity.workspace_id == RequestContext.workspace_id OR
   IS NULL` via `_workspace_scope_clause`. Add
   `tests/api/test_metadata_aspect_cross_tenant.py` exercising the
   deny path.
5. CI lint `scripts/ci/check_entity_picker.py` fails when a `.tsx`
   contains a placeholder matching `urn:aqp:` outside
   `EntityPicker.tsx`.

### 3.4 `[FIX]` Rule 22 — agent boundary

42 hits across 15 files (audit identified 3). Carve a docstring
exception for the four legitimate ledger-writer modules:

- `aqp/agents/runtime.py` — `AgentRuntime` *is* the ledger writer
  (Rule 12)
- `aqp/agents/registry.py` — `persist_spec` of `agent_spec_versions`
- `aqp/agents/evaluation.py` — judge-replay runtime internal
- `aqp/agents/orchestration/runtime.py` + `registry_specs.py` —
  same role for workflows (Rule 41)

Everything else must refactor through DataMCPTools:

| File | New DataMCPTool |
| --- | --- |
| `aqp/agents/strategy_memory.py` | `data.strategy_memory.get_best_params`, `data.strategy_memory.record_observation`, `data.strategy_memory.top_k_for_regime` under `aqp/data/mcp/tools/strategy_memory.py` |
| `aqp/agents/analysis/reflector.py` | Reuse existing `data.analysis.*` tools |
| `aqp/agents/screening/llm_screener.py` | New `data.screening.*` tool |
| `aqp/agents/selection/annotation_writer.py` | New `data.annotations.*` tool |
| `aqp/agents/tools/*.py` | One DataMCPTool per ORM-touching tool |

CI lint `scripts/ci/check_agent_boundary.py` enforces Rule 22 via
AST scan, with the four-file exception list.

### 3.5 `[FIX]` Pydantic V1 and `print()` style sweep

1. One-shot conversion: `\.dict\(` → `.model_dump(`,
   `\.parse_obj\(` → `.model_validate(`.
2. Add ruff `T201` (print) ban-list excluding `scripts/`.
3. Bandit scope expanded from
   `aqp_platform_core` / `aqp_control_plane` to **all** Python
   packages in `.github/workflows/security-scan.yml:60-77`.

### 3.6 Phase 0 deliverable summary

| Deliverable | Target |
| --- | --- |
| `[ADD]` | `alembic/versions/.hashes.lock` |
| `[ADD]` | `scripts/ci/check_migration_immutability.py` |
| `[ADD]` | `scripts/ci/check_migration_chain.py` |
| `[ADD]` | `scripts/ci/check_credential_resolver.py` |
| `[ADD]` | `scripts/ci/check_entity_picker.py` |
| `[ADD]` | `scripts/ci/check_agent_boundary.py` |
| `[ADD]` | `aqp/credentials/stores/datahub_credential_store.py` |
| `[ADD]` | `aqp/data/mcp/tools/strategy_memory.py` |
| `[ADD]` | `metadata_entity_types`, `metadata_entity_urns` in `aqp/cache/keys.py` |
| `[FIX]` | All five DataHub call sites |
| `[FIX]` | `aqp_client/src/routes/metadata/aspects/page.tsx` |
| `[FIX]` | All 11 non-runtime agent modules importing `aqp.persistence` |
| `[ENHANCE]` | `.github/workflows/ci.yml` wires all 5 new lints |
| `[ENHANCE]` | `.pre-commit-config.yaml` |
| `[REMOVE]` | "Grandfathered" comment at `aqp/data/datahub/aspect_puller.py:225-228` |
| `[REMOVE]` | Defensive comment at `alembic/versions/0046_workflow_versioning.py:175-198` |
| `[ENHANCE]` | AGENTS Rule 6 operational procedure |

**Exit criteria**: all 5 CI gates green on a fresh PR that tries
to (a) edit `0046`, (b) read `settings.datahub_token` from a new
module, (c) ship a URN textarea, (d) import `aqp.persistence` from
a non-runtime agent module, (e) introduce a `.dict()` call.

---

## 4. Phase 1 — CI/CD hardening across all subprojects (Weeks 2–6)

### 4.1 `[ADD]` Multi-subproject test matrix

`.github/workflows/ci.yml` today runs unit tests only for
`aqp_platform_core` and `aqp_control_plane`. Extend with a matrix
including `aqp_admin`, `aqp_cli`, `aqp_rl`, `aqp_models`, `aqp_bots`,
`aqp_ingest`, `aqp_kernels`, `aqp_ratelimit`:

```yaml
test-subprojects:
  name: ${{ matrix.subproject }} tests
  strategy:
    fail-fast: false
    matrix:
      include:
        - subproject: aqp_admin
          path: aqp_admin
          extras: "[dev]"
        - subproject: aqp_cli
          path: aqp_cli
          extras: "[dev]"
        - subproject: aqp_rl
          path: aqp_rl
          extras: "[dev]"
        - subproject: aqp_models
          path: aqp_models
          extras: "[dev]"
        - subproject: aqp_bots
          path: aqp_bots
          extras: "[dev]"
        - subproject: aqp_ingest
          path: aqp_ingest
          extras: "[dev]"
        - subproject: aqp_kernels
          path: aqp_kernels
          extras: "[dev]"
        - subproject: aqp_ratelimit
          path: aqp_ratelimit
          extras: "[dev]"
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.11", cache: pip }
    - run: pip install -e ./aqp_platform_core
    - run: pip install -e ./${{ matrix.path }}${{ matrix.extras }}
    - run: cd ${{ matrix.path }} && pytest -ra --cov-report=term
```

### 4.2 `[ADD]` Cross-subproject boundary lint matrix

Generalize the `aqp_control_plane` grep gate:

| Subproject | Allowed roots | Forbidden patterns |
| --- | --- | --- |
| `aqp_control_plane` | `aqp_platform_core`, `aqp_cp` | `aqp.` |
| `aqp_admin` | `aqp_platform_core`, `aqp_admin` | `aqp.`, `aqp_cp.` |
| `aqp_ui` | `aqp_ui` only | `aqp.`, `aqp_cp.` (HTTP-only) |
| `aqp_cli` | `aqp_platform_core`, `aqp_cli` | `aqp.`, `aqp_cp.` |
| `aqp_ide` (Theia ext sources) | `aqp_ide` | `agentic_quant_platform`, `aqp.` |
| `aqp_ingest` | `aqp_platform_core`, `aqp_ingest` | `aqp.api`, `aqp.persistence` |
| `aqp_kernels` | `aqp_platform_core`, `aqp_kernels` | `aqp.persistence`, `aqp.api` |
| `aqp_ratelimit` | `aqp_platform_core`, `aqp_ratelimit` | `aqp.persistence`, `aqp.api` |
| `aqp_rl` | `aqp_platform_core`, `aqp_rl`, plus narrowly: `aqp.llm.providers.router` (R20), `aqp.data.iceberg_catalog` (R18), `aqp.risk.limits` (R38) | other `aqp.*` |
| `aqp_models` | `aqp_platform_core`, `aqp_models`, plus narrowly: `aqp.llm.providers.router` (R2) | other `aqp.*` |
| `aqp_bots` | `aqp_platform_core`, `aqp_bots` | `aqp.api`, `aqp.persistence` |

Implementation: generic `scripts/ci/check_boundary.py [subproject]
[allow-roots]` consumed by a CI matrix.

### 4.3 `[ADD]` Static-analysis layers per subproject

| Wave | Scope | Strictness |
| --- | --- | --- |
| 1 (now) | `aqp_platform_core`, `aqp_control_plane`, `aqp_cli`, `aqp_admin` | `mypy --strict` |
| 2 (Phase 1 end) | `aqp_rl`, `aqp_models`, `aqp_bots`, `aqp_ingest`, `aqp_kernels`, `aqp_ratelimit` | `mypy --strict` for new modules; `strict_optional` for legacy |
| 3 (Phase 4+) | `aqp` | Incremental file-by-file `# mypy: strict` |

### 4.4 `[ADD]` Frontend test discipline

- Vitest coverage threshold wired to PR-blocking at 60% baseline,
  ratcheting 5%/quarter.
- Playwright E2E for: login → tenant pick → workspace open; paper-
  trading recipe → submit → live progress; kill switch fan-out;
  cross-tenant URN deny (drives Rule 33 backend gate end-to-end).

### 4.5 `[ENHANCE]` Rule-specific static checks

| Rule | Static check |
| --- | --- |
| 4 (`_progress.emit`) | AST: ban `redis.publish` outside `aqp/tasks/_progress.py`, `aqp/ws/`, `aqp/cache/` |
| 9 (logging) | ruff `T201` + ban-list |
| 11 (RAG entry points) | AST: ban `redis_client.ft(...)` outside `aqp/rag/` |
| 47 (topology) | AST: ban hardcoded `*-service.svc.cluster.local` URLs outside `aqp/config/`, `aqp_platform/configs/deployment/` |
| 49 (MCP audience) | Static scan of new MCP tool definitions for missing `aud` registration |
| 52 (step-up MFA) | AST: every route in the canonical destructive-route list must carry `Depends(require_step_up(...))` in its decorator stack |
| 55 (BYOK brokers) | AST: ban `settings.alpaca_*` / `settings.ibkr_*` / `settings.tradier_*` / `settings.polygon_*` outside `aqp/credentials/stores/broker_credential_store.py` |

Each check ships with `tests/ci/test_<rule>_lint.py`.

### 4.6 `[REMOVE]` `|| true` masks in CI

`.github/workflows/ci.yml:27,29` silently swallow ruff failures.
Same for bandit at `.github/workflows/security-scan.yml:68-69`.
Remove all `|| true` once the existing tree passes cleanly.

### 4.7 `[ADD]` Renovate / Dependabot governance

- Renovate config groups transitive ML/LLM, infrastructure, and
  frontend deps separately.
- Auto-merge for patch bumps on `aqp_platform_core` / `aqp_cli`
  only after the matrix CI is green.
- Manual review required for any bump touching `cryptography`,
  `litellm`, `pyiceberg`, `sqlalchemy`, `alembic`, `fastapi`,
  `pydantic`.

---

## 5. Phase 2 — Container & supply chain hardening (Weeks 4–10)

### 5.1 `[ENHANCE]` Chainguard Wolfi base migration

Today `aqp_platform/Dockerfile` is the master Dockerfile. Plan:

1. Pin every Python base layer to `cgr.dev/chainguard/python:3.11`
   (distroless, glibc — required for `numpy`/`pyarrow`/`torch`
   native wheels; Alpine/musl breaks them).
2. Pin every Node base layer to `cgr.dev/chainguard/node:20`.
3. Multi-stage builder with `uv` (`uv sync --frozen`) replaces `pip`
   for reproducibility.
4. Runtime stage runs as UID 65532 (`USER 65532:65532`).
5. Three named images:
   - `aqp-edge` (Envoy cell router; see Phase 3)
   - `aqp-api` (FastAPI + Celery worker shared image)
   - `aqp-agent-sandbox` (gVisor RuntimeClass target; see Phase 5)

`.github/workflows/build-multi-arch.yml` already produces multi-arch
images. Wave-in Chainguard one image at a time with canary
digest-pin overlay in `aqp_platform/deployments/`.

### 5.2 `[ADD]` Cosign keyless OIDC signing + SBOM attestation

```yaml
# .github/workflows/build-multi-arch.yml (additive job)
permissions:
  id-token: write
  packages: write
  contents: read

build-and-sign:
  steps:
    - uses: docker/build-push-action@v6
      id: build
      with:
        tags: ghcr.io/julianwileymac/aqp/${{ matrix.image }}:${{ github.sha }}
        push: true
        provenance: true
    - uses: sigstore/cosign-installer@v3
    - name: Cosign keyless sign (Rekor transparency log)
      run: |
        cosign sign --yes \
          ghcr.io/julianwileymac/aqp/${{ matrix.image }}@${{ steps.build.outputs.digest }}
    - name: syft SBOM
      run: |
        syft ghcr.io/julianwileymac/aqp/${{ matrix.image }}@${{ steps.build.outputs.digest }} \
          -o cyclonedx-json=sbom-${{ matrix.image }}.json
    - name: Cosign attest SBOM
      run: |
        cosign attest --yes --predicate sbom-${{ matrix.image }}.json \
          --type cyclonedx \
          ghcr.io/julianwileymac/aqp/${{ matrix.image }}@${{ steps.build.outputs.digest }}
    - name: grype scan fail-on-high
      run: grype sbom:./sbom-${{ matrix.image }}.json --fail-on high
```

### 5.3 `[ADD]` Kyverno admission policies

New top-level directory:

```
aqp_platform/deployments/kubernetes/security/
  kyverno/
    cluster-policies/
      00-verify-signatures.yaml      # only cosign-signed AQP images
      01-require-pss-restricted.yaml # enforce restricted PSS
      02-require-runtime-class.yaml  # agents must use gvisor RuntimeClass
      03-no-host-network.yaml
      04-no-privilege-escalation.yaml
      05-required-labels.yaml        # tenant_id, cell_id, env required
  pod-security/
    namespaces/                      # one ns per tenant per cell
```

`imageReferences` scoped to `ghcr.io/julianwileymac/aqp/*` with
keyless signature subject matching the GHA workflow identity.

### 5.4 `[ADD]` Pod Security Standards (restricted)

Every namespace gets labels:

```yaml
pod-security.kubernetes.io/enforce: restricted
pod-security.kubernetes.io/enforce-version: latest
pod-security.kubernetes.io/audit: restricted
pod-security.kubernetes.io/warn: restricted
```

Pod template for all AQP pods:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  seccompProfile: { type: RuntimeDefault }
containers:
  - securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities: { drop: ["ALL"] }
```

### 5.5 `[REMOVE]` Outdated rollback artifacts from default build

`aqp_platform/rollback/rpi_k8s_sdk/` and adjacent `legacy-management/`
paths must not be in the default image build matrix. Constrain
`build-multi-arch.yml` to build them only on explicit
`workflow_dispatch` with `rollback=true` input flag.

### 5.6 Phase 2 deliverables

| Action | Target |
| --- | --- |
| `[ENHANCE]` | All Dockerfiles → Chainguard Wolfi |
| `[ADD]` | Cosign keyless sign + Rekor entry in CI |
| `[ADD]` | syft SBOM + cosign attestation |
| `[ADD]` | grype `--fail-on high` gate |
| `[ADD]` | Kyverno cluster policies (signature verify, PSS, runtime class, no privilege escalation, required labels) |
| `[ENHANCE]` | Every namespace labeled PSS restricted |
| `[ADD]` | `aqp-agent-sandbox` image with `runtimeClassName: gvisor` |
| `[REMOVE]` | `\|\| true` masks in CI (final pass) |

---

## 6. Phase 3 — Cell topology over existing tenancy strategies (Weeks 6–14)

The blueprint's "cell" is a *deployment* concept; AQP's existing
`TenancyStrategy` is an *application/data-layer* concept. They must
compose.

### 6.1 The mapping

| Blueprint cell tier | AQP `TenancyStrategy` | Deployment shape | Compliance posture |
| --- | --- | --- | --- |
| `shared-std` (free, dev, low-throughput) | `SharedSchemaRLSStrategy` | One K8s ns per cell; many tenants; RLS-enforced isolation in shared Postgres | SOC 2 baseline |
| `shared-prem` (paid, multi-tenant) | `SchemaPerTenantStrategy` | One K8s ns per cell; one Postgres schema per tenant in shared cluster | SOC 2 Type II |
| `silo-reg` (regulated, isolated) | `DatabasePerEnterpriseStrategy` | One K8s ns per cell, one cell per tenant, dedicated Postgres cluster | FINRA / ISO 27001 |
| `silo-custom` (custom contract) | `HybridStrategy` | Per-customer agreement | Custom |

A **cell** = `(tier, region, az, k8s_namespace)`. The
`TenancyStrategy` factory at `aqp/tenancy/factory.py::get_tenancy_factory`
already returns the right strategy per-request via `RequestContext`.
Cell binding adds `RequestContext.cell_id` propagating through
Postgres GUC, OTEL spans, and audit events.

### 6.2 `[ADD]` Cell registry — extend the topology service

Today the topology service (Rule 47) returns service URLs from
`aqp_platform/configs/deployment/topology.yaml`. Extend it:

```yaml
# aqp_platform/configs/deployment/topology.yaml (additive section)
cells:
  - id: cell-shared-std-us-east-1a
    tier: shared-std
    tenancy_strategy: shared_schema_rls
    region: us-east-1
    availability_zone: us-east-1a
    k8s_namespace: cell-shared-std-us-east-1a
    capacity_max_tenants: 5000
    state: active            # active | draining | suspended | maintenance
    routes:
      api: https://us-east-1a.shared-std.aqp.fund
      ws:  wss://us-east-1a.shared-std.aqp.fund/ws
  - id: cell-silo-reg-acme
    tier: silo-reg
    tenancy_strategy: database_per_enterprise
    region: us-east-1
    availability_zone: us-east-1a
    k8s_namespace: cell-silo-reg-acme
    capacity_max_tenants: 1
    state: active
    pinned_tenants: [tenant_acme]
```

New ORM table `cells` via Alembic `0081_cell_registry.py` mirrors
this YAML; YAML stays the bootstrap seed and live updates go through
control-plane `/manage/cells/*` routes. `Cell.state` transitions
through `provisioning → active → draining → decommissioning →
archived`.

### 6.3 `[ADD]` Cell-aware `RequestContext`

```python
# aqp/auth/context.py (additive fields)
@dataclass(frozen=True)
class RequestContext:
    user_id: str | None
    workspace_id: str | None
    project_id: str | None
    experiment_id: str | None
    test_id: str | None
    cell_id: str | None                 # NEW
    region: str | None                  # NEW
    tenancy_strategy_alias: str | None  # NEW
    ...
```

Propagation:
- `aqp.tenancy.runtime_context.set_tenancy_context(ctx)` (Rule 51)
  also sets `SET LOCAL app.current_cell_id = '...'` alongside
  `app.current_workspace_id`.
- OTEL span attributes auto-include `cell.id`, `cell.region`,
  `cell.tier`.
- Every audit event (`security_audit_events`, `data_lineage_events`,
  the hash-chained audit log at Alembic `0079`) gets a `cell_id`
  column via `0082_audit_cell_id_column.py`.

### 6.4 `[ADD]` Cell router (Envoy) replaces single-container client

`aqp_client/` is the canonical client (per its `CUTOVER.md`); the
**proxy** half of ADR 002 (Python FastAPI) routes `/api/*`, `/ws/*`,
`/manage/*`, `/static`. Replace with **Envoy + ext_authz**:

```
[ user / agent ]
       │ TLS
       ▼
[ Cloudflare Tunnel (aqp.fund) ]
       │
       ▼
[ aqp-edge — Envoy (HTTP-only) ]
       │ ext_authz → Pomerium (for /manage/*)
       │ ext_authz → aqp-tenant-router (resolves tenant → cell)
       ▼
[ aqp-cell-<id>-api  (FastAPI) ]
       │
       ▼  Linkerd mTLS
[ aqp-cell-<id>-workers (Celery, gVisor for agents) ]
       │
       ▼
[ aqp-cell-<id>-postgres ]   [ aqp-cell-<id>-minio ]
```

`aqp-tenant-router` is a small Go/Rust service that:
1. Reads the user's JWT (`sub`, `workspace_id`, `tenant_id`).
2. Queries the `cells` registry (cached, sub-ms hot path).
3. Returns the cell endpoint via Envoy xDS or an `x-aqp-cell`
   header for the next-hop Envoy.

Cutover plan (Slack-pattern, 5-minute drain granularity):

| Week | Step | Rollback |
| --- | --- | --- |
| 6 | Deploy `aqp-edge` Envoy in parallel with the Python proxy; DNS unchanged | Disable `aqp-edge` Service |
| 7 | DNS canary 10% traffic to `aqp-edge` | DNS revert |
| 8 | 50% traffic | DNS revert |
| 9 | 100% traffic; Python proxy still buildable | Switch routing back via overlay |
| 10 | Remove Python proxy from `aqp_platform/build/docker/aqp-client/` | Restore previous tag |

### 6.5 `[ENHANCE]` Per-cell K8s manifest overlay

`aqp_platform/deployments/kubernetes/overlays/` has `dev/staging/prod`.
Add a third axis:

```
aqp_platform/deployments/kubernetes/
  base/                       # unchanged
  overlays/
    dev/
    staging/
    prod/
  cells/
    shared-std-us-east-1a/    # per-cell overlay
    shared-prem-us-east-1a/
    silo-reg-acme/
```

`kustomize build aqp_platform/deployments/kubernetes/cells/<id>`
emits a complete cell. Argo CD `ApplicationSet` stamps cells from
the `cells` registry.

### 6.6 `[REMOVE]` Python FastAPI cell proxy

Once Phase 3 step 5 lands (week 10), delete the proxy code and
Dockerfile. Keep a tagged release for regression.

### 6.7 Phase 3 deliverables

| Action | Target |
| --- | --- |
| `[ADD]` | Alembic `0081_cell_registry.py` |
| `[ADD]` | Alembic `0082_audit_cell_id_column.py` |
| `[ENHANCE]` | `aqp/auth/context.py::RequestContext` adds `cell_id`, `region`, `tenancy_strategy_alias` |
| `[ENHANCE]` | `aqp/tenancy/runtime_context.py` sets `app.current_cell_id` GUC |
| `[ENHANCE]` | `aqp_platform/configs/deployment/topology.yaml` adds `cells` section |
| `[ADD]` | `aqp-edge` Envoy image + manifests |
| `[ADD]` | `aqp-tenant-router` Go/Rust service |
| `[ADD]` | `/manage/cells/*` routes in `aqp_control_plane` |
| `[ADD]` | `aqp_platform/deployments/kubernetes/cells/<id>/` overlays + Argo `ApplicationSet` |
| `[REMOVE]` | Python FastAPI proxy from `aqp_platform/build/docker/aqp-client/` |

---

## 7. Phase 4 — Service mesh & workload identity (Weeks 10–18)

### 7.1 `[ADD]` Linkerd 2.16

**Why Linkerd over Istio**: blueprint's argument holds for AQP today.
The control plane is two pods. The Rust data plane is a fraction of
the memory of Envoy + Pilot. Per-cell installs are tractable. Istio
would be defensible only if the team already had operator experience
and needed L7 policies that ext_authz at the edge cannot already
deliver — neither is true.

**Action**:
1. Install Linkerd 2.16 per-cell (one control plane per cell, not
   global). Cluster-wide installs are an anti-pattern for the cell
   model.
2. Annotate every `aqp-cell-*` namespace with
   `linkerd.io/inject: enabled`.
3. mTLS-by-default for every pod-to-pod call inside the cell.
4. Cross-cell calls go through the Envoy cell router; no mesh
   federation. Cells are isolation domains.
5. Add `linkerd-viz` per-cell for golden-signal dashboards.

### 7.2 `[ADD]` SPIRE 1.10 + SPIFFE workload identity

Federate with the existing `M2MTokenIssuer` (Rule 27):

1. Deploy SPIRE Server per cell (or one regional SPIRE Server with
   per-cell SPIRE Agents — choose based on cross-cell ops needs).
2. Issue SVID per workload: `spiffe://aqp.fund/cell/<cell-id>/<sa>`.
3. Replace the kubelet-bound service account token usage in
   `aqp/auth/m2m.py` with SPIFFE Workload API. Keep the existing
   `M2MTokenIssuer` interface; swap the implementation behind the
   `IdentityProviderMeta` registry (Rule 27).
4. Document the trust domain in
   `aqp_docs/docs/concepts/identity/spiffe-workload-identity.md`.
5. **Why this matters**: the current `M2MTokenIssuer` mints
   short-lived JWTs but they are still bearer tokens. SPIFFE-bound
   identities are workload-attested via the platform (UID, cgroup,
   selectors) — much harder to steal, automatically rotated.

### 7.3 `[ADD]` Cedar policy engine for application authz

Place Cedar **alongside** the existing
`aqp_platform_core.auth.resource_filter` (Rule 45), not replacing it.
Resource filter stays for the high-throughput list-endpoint case;
Cedar evaluates per-action decisions for `/manage/*` and the
agent-sandbox tool surface.

```cedar
// aqp_platform/configs/cedar/policies/cells.cedar
permit (
  principal,
  action == Action::"manage_cell",
  resource is Cell
)
when {
  principal has org_id
  && resource.tenant_org_id == principal.org_id
  && principal.has_role("cell_operator")
};

forbid (
  principal,
  action,
  resource
)
when {
  resource has data_classification
  && resource.data_classification == "regulated"
  && !principal.has_clearance("regulated")
};
```

Evaluation point: a new `aqp/api/security_cedar.py::require_cedar`
FastAPI dep that wraps the existing `RequestContext` + a Cedar
context dict. Returns the policy decision and the matched policy IDs
(audited).

### 7.4 `[ENHANCE]` OPA is confined to cluster admission

OPA is great at cluster-side decisions (Gatekeeper / Kyverno is an
alternative). Cedar is dramatically better at *application* authz.
Do not mix domains.

### 7.5 `[ADD]` Pomerium identity-aware proxy on `/manage/*`

The `aqp_control_plane` `/manage/*` API and `aqp_admin/` already
require admin auth via `IdentityProvider`. Front them with Pomerium
in front of the cell router (Section 6.4 diagram). Pomerium:
- Validates the user's primary IdP token (Auth0 / Entra).
- Performs the **step-up MFA prompt** (Rule 52) before forwarding.
- Adds `Cf-Pomerium-Jwt-Assertion` header for backend audit
  consumption (mirrors the existing
  `CloudflareAccessProvider` pattern at
  `aqp/auth/providers/cloudflare_access.py`).
- Per-route policy reads from the same Cedar engine.

### 7.6 `[ADD]` `vault-secrets-operator` for runtime secret hydration

Replace the manual Kubernetes Secret injection pattern (used in
`aqp_platform/deployments/kubernetes/base/*/secrets.yaml`) with
HashiCorp `vault-secrets-operator` CRDs:

```yaml
apiVersion: secrets.hashicorp.com/v1beta1
kind: VaultStaticSecret
metadata:
  name: aqp-cell-postgres-credentials
  namespace: cell-shared-std-us-east-1a
spec:
  mount: cells/shared-std/postgres
  path: cell-shared-std-us-east-1a
  destination: { create: true, name: postgres-credentials }
  refreshAfter: 30m
  rolloutRestartTargets:
    - kind: Deployment
      name: aqp-cell-api
```

`CredentialResolver` (Rule 26) gains a new `VaultStaticSecretStore`
that reads the projected `Secret` directly — but the *envelope key*
for `vault_transit.encrypt` (`aqp/credentials/vault_transit.py`)
stays in Vault Transit, not Kubernetes.

### 7.7 Phase 4 deliverables

| Action | Target |
| --- | --- |
| `[ADD]` | Per-cell Linkerd 2.16 control plane manifests |
| `[ADD]` | `linkerd.io/inject: enabled` on every `aqp-cell-*` namespace |
| `[ADD]` | SPIRE Server + Agent manifests per cell |
| `[ENHANCE]` | `aqp/auth/m2m.py::M2MTokenIssuer` SPIFFE-backed |
| `[ADD]` | `aqp_docs/docs/concepts/identity/spiffe-workload-identity.md` |
| `[ADD]` | Cedar policy engine + `aqp/api/security_cedar.py::require_cedar` |
| `[ADD]` | `aqp_platform/configs/cedar/policies/*.cedar` |
| `[ADD]` | Pomerium in front of `/manage/*` |
| `[ADD]` | `vault-secrets-operator` per-cell + `VaultStaticSecretStore` in `aqp/credentials/stores/` |

---

## 8. Phase 5 — Per-tenant MCP & agent sandbox (Weeks 12–20)

The current MCP catalog is *one* `aqp-data-mcp` + *one* `aqp-codebase-mcp`
shared across all tenants, with tenant isolation enforced inside
each tool body via `RequestContext` (Rules 22, 33, 49). This is
secure but operationally brittle — a runaway agent in one tenant
can starve the MCP catalog for everyone.

### 8.1 `[ADD]` Per-tenant MCP server isolation

Run one MCP server *per tenant per cell*. Same image, scoped resource
limits, scoped database connection, scoped LLM-router rate-limit
budget. Tenants in the `shared-std` tier share a pool of MCP servers
with **per-tenant Linux cgroups** and a hard wall-clock budget; the
`shared-prem` and `silo-reg` tiers get dedicated MCP pods.

Topology:

```
cell-<id>/
  mcp-pool/                       # shared-std: 1 deployment, N tenant cgroups
    aqp-data-mcp-pool-deployment
    aqp-codebase-mcp-pool-deployment
  mcp-tenant-<tenant_id>/         # shared-prem and silo-reg: per tenant
    aqp-data-mcp-<tenant_id>
    aqp-codebase-mcp-<tenant_id>
```

`aqp/data/mcp/` gains a new `tenant_router.py` that on every
incoming MCP request:
1. Validates `aud` (Rule 49) — must match the cell-MCP canonical
   URI for the calling tenant.
2. Looks up the tenant's MCP pod via the topology service.
3. Proxies the request, attaching short-lived workload SVIDs
   (Section 7.2).

### 8.2 `[ADD]` Biscuit capability tokens (alongside RFC 8693)

`TokenExchangeBroker` (Rule 54) already mints delegated JWTs.
Biscuit gives a *capability-attenuated* alternative for the
agent-to-tool path:

- Initial delegation: `TokenExchangeBroker` mints a Biscuit with the
  full set of capabilities the agent could possibly need.
- Per-tool-call: the agent calls `biscuit.attenuate` to narrow the
  capability set to **exactly** the tool + args of this call, then
  presents the attenuated biscuit to the MCP server.
- The MCP server verifies the biscuit, checks the capability matches
  the tool descriptor's required capability, and emits the existing
  audit event with `actor_kind="agent"` (Rule 54).

This closes the "compromised agent reuses its broad JWT" gap.

### 8.3 `[ADD]` gVisor RuntimeClass for agent-sandbox-pool

The agent sandbox pool runs **untrusted code** in three contexts:
1. LLM-emitted Python in the AST sandbox
   (Rule 39 / `aqp/data/expressions_dsl.py`) — this is already AST-
   constrained, but defense in depth wants gVisor too.
2. Notebook kernels for the Dagster sandbox
   (`aqp/dagster/sandbox/` — Rule 32).
3. Future agent-emitted strategy code (LEAN translator output,
   `aqp/strategies/lean/translator.py` — Rule 35).

Each gets the `runtimeClassName: gvisor` annotation and Kyverno
Rule `02-require-runtime-class.yaml` (Phase 2) enforces it for the
`aqp-agent-sandbox` pool.

### 8.4 `[ADD]` Content-hash pinning of MCP tool descriptions

Today new MCP tools are registered via `@register_data_mcp_tool` and
the descriptor is read at module import. Extend the spec-versioning
pattern (Rules 13, 15, 17, 24, 41) to MCP tools:

1. New ORM table `mcp_tool_versions` via Alembic
   `0083_mcp_tool_versioning.py`:
   - `tool_name`, `descriptor_hash` (SHA-256 of canonical JSON
     representation), `descriptor_json`, `created_at`,
     `created_by`, `cell_id`.
2. On boot, every MCP server snapshots its tool catalog and
   `INSERT ... ON CONFLICT DO NOTHING`. A hash change inserts a new
   row.
3. Every agent run's `agent_runs_v2` row records the
   `mcp_tool_descriptor_hashes` set used. Replay verifies the same
   set is presently registered (or runs against the snapshot if
   anyone wants "replay against the exact tool surface at the
   time").

### 8.5 `[ADD]` Audience-bound tokens for cross-cell calls

Cross-cell calls are the **highest-risk** path. Today there is no
explicit policy. New rule:

- All cross-cell MCP calls require an audience-bound short-lived
  token where `aud == cell-<destination-cell-id>` and `iss ==
  cell-<source-cell-id>` and `nbf/exp` enforce a 60-second window.
- Carried in a `Cell-Bound-Authorization` header (separate from
  `Authorization` so the cell router can validate before
  forwarding).
- Mint via the SPIRE-backed `M2MTokenIssuer` (Section 7.2) with
  a per-cell minting policy bound to the workload SVID.

### 8.6 Phase 5 deliverables

| Action | Target |
| --- | --- |
| `[ADD]` | `aqp/data/mcp/tenant_router.py` |
| `[ADD]` | Per-tenant MCP K8s manifests (Helm chart in `aqp_platform/deployments/`) |
| `[ADD]` | Biscuit capability token integration alongside existing `TokenExchangeBroker` |
| `[ADD]` | gVisor `RuntimeClass` cluster object + `aqp-agent-sandbox` pool |
| `[ENHANCE]` | `aqp/data/mcp/registry.py` emits `descriptor_hash` on every tool registration |
| `[ADD]` | Alembic `0083_mcp_tool_versioning.py` |
| `[ENHANCE]` | `aqp/agents/runtime.py` records `mcp_tool_descriptor_hashes` on `agent_runs_v2` |
| `[ADD]` | `Cell-Bound-Authorization` header + cell-router validation in `aqp-edge` |

---

## 9. Phase 6 — Data plane silo per cell (Weeks 16–24)

The current data plane is **shared globally**: one Postgres, one
Iceberg catalog, one Redis, one MLflow. This is the highest-impact
piece of the cell story — moving it per-cell is what gives a
regulated tenant a defensible compliance argument.

### 9.1 `[ADD]` Postgres per cell

**Operator choice**: CloudNativePG (portable) for any on-prem / k3s /
EKS-with-no-Aurora deployment; Aurora-per-cell for AWS-native. The
two coexist via the existing `TenancyStrategy` factory.

Topology (per cell):

```
cell-<id>/
  postgres/
    cluster.yaml             # CNPG Cluster CRD, 3 replicas, async PITR
    pgvector-extension.yaml  # for the existing Rule 11 RAG (Alembic 0045)
    backup.yaml              # to per-cell MinIO/S3
  redis/
    helm-values.yaml         # Bitnami chart, per-cell
  mlflow/
    deployment.yaml          # connects to per-cell postgres + minio
  questdb/                   # per-cell tick database (optional)
  iceberg-rest/              # per-cell Iceberg REST catalog
```

Migration strategy:

| Tier | Migration shape |
| --- | --- |
| `shared-std` | Single CNPG cluster per cell with RLS-enforced isolation; no change to row-level access patterns; per-row tenant scoping via existing `app.current_workspace_id` GUC |
| `shared-prem` | Same single CNPG cluster but switch from RLS to one schema per tenant — the existing `SchemaPerTenantStrategy` already implements the GUC-driven schema selection at request time |
| `silo-reg` | One dedicated CNPG cluster per regulated tenant. `DatabasePerEnterpriseStrategy` returns a separate `Engine` per tenant from a pool keyed on tenant ID. PgBouncer fronts each cluster to keep the connection count bounded |

The migration sequence is **outside-in**:
1. Provision the new per-cell Postgres clusters (Argo CD
   `ApplicationSet` over `cells` registry).
2. Backfill: `pg_dump` from the global cluster → per-cell cluster,
   scoped to the cell's tenant set.
3. Dual-write window: `aqp.persistence.db.SessionLocal` writes to
   both global and per-cell Postgres for the cell's tenants (gated
   by `AQP_CELL_DUAL_WRITE=<cell_id>`).
4. Reads cut over per-tenant to the per-cell engine via the
   `TenancyStrategy.get_engine(ctx)` method (already the indirection
   point).
5. Tear down global writes for migrated tenants; drop dual-write
   flag.

### 9.2 `[ADD]` Object storage per cell

- **MinIO per cell** for on-prem / hybrid; **S3 per cell** (with
  bucket-per-cell) for AWS-native.
- Iceberg warehouse path changes from a single
  `file:///C:/aqp-warehouse/iceberg` to per-cell:
  `s3://aqp-cell-<id>-warehouse/iceberg`.
- `iceberg_catalog.append_arrow` (Rule 3) reads the warehouse URI
  from `topology.yaml` resolved by cell. No changes to
  `medallion_layer` validation.
- **Object Lock COMPLIANCE mode** on the `audit/` prefix per cell.
  This makes the audit-immutability story (Section 10) survive a
  rogue admin.

### 9.3 `[ADD]` Per-cell KMS CMK

- AWS: one KMS CMK per cell, KMS key policy restricts use to the
  cell's IAM role.
- On-prem / hybrid: per-cell Vault Transit key (extends the existing
  `aqp/credentials/vault_transit.py` to be cell-aware via the new
  `RequestContext.cell_id`).
- DEK rotation: 90-day automatic via the operator.

### 9.4 `[ADD]` Per-cell pgvector + Redis

Alembic `0045_pgvector_foundation.py` already lays the foundation.
Per-cell deployment:

- pgvector lives **in the per-cell Postgres** (a `vectors` schema).
- Redis per cell (Bitnami chart, 3-node Sentinel for `shared-prem`+;
  single-node for `shared-std`).
- The hierarchical RAG (Rule 11) at `aqp/rag/hierarchy.py` resolves
  the Redis URL via the topology service (Rule 47) and the
  pgvector connection via the same `TenancyStrategy.get_engine`.

### 9.5 `[ADD]` MLflow per cell

Currently MLflow is referenced from `aqp/mlops/` for autolog hooks
(Rule referenced indirectly). Per-cell MLflow:

- One MLflow Tracking Server deployment per cell, backed by per-cell
  Postgres + per-cell MinIO for artifacts.
- The `aqp_models` package (Rule for `aqp_models` already isolates
  the ML logic) is the only consumer; it reads the tracking URI from
  the topology service.
- The Predictor Hub (per `aqp_models/AGENTS.md`) caches predictors
  per-cell.

### 9.6 `[ADD]` Per-cell streaming (Kafka / Redpanda) — optional

The current `aqp/streaming/` (Rules around streaming admin) uses one
global Kafka. For the `shared-std` and `shared-prem` tiers, this
stays. For `silo-reg`, a per-cell Redpanda (single-binary, lower
overhead than Kafka).

Decision deferred — only add per-cell Kafka/Redpanda when the first
`silo-reg` tenant requests it (avoid over-provisioning).

### 9.7 Phase 6 deliverables

| Action | Target |
| --- | --- |
| `[ADD]` | CNPG `Cluster` CRD per cell |
| `[ADD]` | Per-cell Redis (Bitnami chart) |
| `[ADD]` | Per-cell MinIO / S3 bucket with Object Lock COMPLIANCE on `audit/` |
| `[ADD]` | Per-cell MLflow tracking server |
| `[ADD]` | Per-cell Iceberg REST catalog (replaces global SQL catalog) |
| `[ENHANCE]` | `aqp/data/iceberg_catalog.py::append_arrow` resolves warehouse URI per cell |
| `[ENHANCE]` | `aqp/credentials/vault_transit.py` is cell-aware via `RequestContext.cell_id` |
| `[ENHANCE]` | `aqp.persistence.db.SessionLocal` resolves engine per cell via `TenancyStrategy` |
| `[ADD]` | `AQP_CELL_DUAL_WRITE` feature flag for staged migration |
| `[ADD]` | Dual-write backfill script `scripts/cells/dual_write_backfill.py` |

---

## 10. Phase 7 — Audit immutability & reconstruction (Weeks 18–26)

Building on Alembic `0079_audit_log_hash_chain.py` and
`0060_openlineage_outbox.py` + `0061_lineage_signing_archive.py`.

### 10.1 `[ENHANCE]` Hash-chained audit lake → S3 Object Lock COMPLIANCE

Today the audit hash chain lives in Postgres. Per-cell deployment:

1. The hash-chained `audit_log` Postgres table stays the hot
   write path.
2. An hourly Celery beat task (`aqp.tasks.audit_lake_tasks.flush`)
   serializes the closed segment to Iceberg under
   `aqp_gold_audit.events_<cell_id>` and copies the manifest to
   `s3://aqp-cell-<id>-warehouse/audit/<yyyy>/<mm>/<dd>/` with
   **Object Lock COMPLIANCE** retention = 7 years.
3. The previous segment's tip hash + the new segment's tip hash are
   anchored to the OpenLineage outbox (extends `0060`/`0061`) — a
   detached signed entry per hour.
4. Tip hash also written to a cell-external **transparency log**
   (Rekor instance, or AWS QLDB, or RFC 3161 TSA — pick one):
   - Rekor: free, public, ideal for `shared-std`/`shared-prem`.
   - QLDB: private, AWS-only, ideal for `silo-reg`-on-AWS.
   - RFC 3161 TSA: external timestamping, ideal for `silo-reg`-on-prem.
5. Reconstruction: any auditor can request "show me the audit chain
   for cell X between dates A and B" and the system replays from
   Iceberg, re-computes the chain, verifies against the anchored
   tips.

### 10.2 `[ADD]` Replay harness leverages hash-locked specs

The pre-existing hash-locked spec versions (Rules 13, 15, 17, 24,
41, 43) plus the new MCP tool hash (Section 8.4) make this
straightforward. New `aqp/audit/replay.py`:

```python
def replay_run(
    *,
    run_id: str,
    cell_id: str,
    target_environment: ReplayEnvironment = ReplayEnvironment.AUDIT_SHADOW,
) -> ReplayReport:
    """Re-execute an agent / workflow / RL / analysis / backtest run
    against the exact spec + MCP tool surface that existed at run time.

    1. Load the spec_version_id from the run ledger row.
    2. Pin the MCP tool descriptors by mcp_tool_descriptor_hashes.
    3. Set a deterministic LLM seed via router_complete cache_key.
    4. Execute in the AUDIT_SHADOW environment (read-only).
    5. Compare the new run's output hash to the original output hash.
    """
```

Replay environments:

| Env | Side effects | Purpose |
| --- | --- | --- |
| `AUDIT_SHADOW` | None — all writes diverted to a per-run shadow Postgres schema | Compliance verification |
| `INCIDENT_REPRO` | None — all writes diverted; output diffed against original | Bug bisection |
| `MODEL_REVALIDATION` | Writes to a marked "replay-N" branch of `agent_runs_v2`; never touches the original | Model behaviour over time |

### 10.3 `[ENHANCE]` Bipartite lineage v2 → cell-aware

Alembic `0059_lineage_graph_v2.py` already adds
`lineage_dataset_vertex` + `lineage_transform_vertex` +
`lineage_edge` (Rule 48). Add `cell_id` columns via
`0084_lineage_cell_id.py` and update the
`BipartiteGraphObserver` to write cell-scoped vertices.

The DataMCP tools `data.lineage.ancestry` / `data.lineage.impact`
gain a `--cross-cell` flag, default `false` — cross-cell lineage
walks require explicit operator opt-in and emit a step-up MFA
prompt.

### 10.4 `[ADD]` Regulatory-grade evidence bundle

A new control-plane endpoint
`POST /manage/evidence-bundles` for a given `(tenant_id, date_range,
event_kind)` produces a downloadable .tar.zst containing:

- All audit-log segments (raw + tip-hashes + transparency anchor
  proofs).
- All spec snapshots referenced by those audit rows.
- All MCP tool descriptor hashes.
- All `data_lineage_events` and bipartite graph vertices in range.
- A cryptographic manifest signed by the cell's signing key
  (Section 10.1).

This is the artifact a FINRA / SEC examiner walks away with. The
construction must be deterministic — same inputs, byte-identical
output.

### 10.5 Phase 7 deliverables

| Action | Target |
| --- | --- |
| `[ADD]` | `aqp/tasks/audit_lake_tasks.py::flush` hourly beat task |
| `[ADD]` | Object Lock COMPLIANCE policy on `audit/` prefix per cell |
| `[ENHANCE]` | OpenLineage outbox emits hourly tip-hash anchors |
| `[ADD]` | Transparency-log anchor sink (Rekor / QLDB / RFC 3161 TSA) |
| `[ADD]` | `aqp/audit/replay.py` replay harness |
| `[ADD]` | Replay shadow Postgres schema lifecycle |
| `[ADD]` | Alembic `0084_lineage_cell_id.py` |
| `[ADD]` | `POST /manage/evidence-bundles` route |

---

## 11. Phase 8 — Multi-region & disaster recovery (Weeks 24–36)

### 11.1 `[ADD]` Cell drain primitives

Slack-pattern, 1% traffic-shift granularity:

- New `/manage/cells/<id>/drain` route on `aqp_control_plane`.
- Sets `Cell.state = draining`; the cell router stops sending new
  tenant sessions; existing sessions complete or are migrated.
- A drain has three phases:
  1. **Soft drain**: new connections rejected with 503 Retry-After.
  2. **Tenant migration**: pinned tenants' sessions migrate to a
     target cell (state replicated via per-tenant snapshot + replay
     window).
  3. **Hard drain**: all sessions terminated; pods scaled to zero.
- Auto-rollback if `Cell.state == draining` and any cell-scoped SLI
  drops below threshold within 10 minutes.

### 11.2 `[ADD]` Cross-region cells for `silo-reg`

The `silo-reg` tier ships per-region replicas with an active-passive
RPO < 5 minutes and RTO < 30 minutes:

- Active region: full read/write.
- Passive region: CNPG replica with async streaming replication +
  per-hour S3 manifest mirror via Object Lock-aware cross-region
  replication.
- Failover orchestrated by the control-plane
  `POST /manage/cells/<id>/failover-to-<region>` route.
- Test quarterly via `scripts/dr/run_failover_drill.py` (script
  drives every step end-to-end against a staging cell pair).

### 11.3 `[ENHANCE]` Kill-switch propagation budget

Today `/portfolio/kill_switch` fans out to 12 routes (Rule 52). In
the multi-cell world, the kill-switch must cross-cell fan out within
budget:

- p99 ≤ 3 seconds **across all cells in the user's tenancy**.
- Implementation: kill switch publishes to a global Redis Stream
  (`aqp:killswitch:events`) consumed by every cell's
  `aqp.tasks.killswitch_consumer` worker — cell consumers act
  locally (workload runtime halts, etc.) and emit a confirmation
  back on `aqp:killswitch:confirmations`.
- Acceptance test in `tests/dr/test_killswitch_cross_cell.py`
  enforces the SLO.

### 11.4 Phase 8 deliverables

| Action | Target |
| --- | --- |
| `[ADD]` | `/manage/cells/<id>/drain` route |
| `[ADD]` | Tenant migration plumbing |
| `[ADD]` | Cross-region CNPG replication for `silo-reg` |
| `[ADD]` | `/manage/cells/<id>/failover-to-<region>` route |
| `[ADD]` | `scripts/dr/run_failover_drill.py` quarterly drill |
| `[ENHANCE]` | Kill-switch fans out cross-cell; SLO test |

---

## 12. Repository split finalization (parallel to all phases)

The current split is **in flight**. Five subprojects are documented
but lack mechanical isolation gates. Five subprojects are
documented but lack CI test coverage. The deprecation shims
`aqp/ml/` and `aqp/rl/` still emit `DeprecationWarning` only — no
removal deadline.

### 12.1 `[ENHANCE]` Per-subproject AGENTS.md compliance audit

For each of the 14 subprojects, run a one-shot audit:

```bash
# scripts/repo/audit_subproject.sh <subproject>
set -e
SUB="$1"
echo "=== Auditing ${SUB} ==="

# 1. AGENTS.md exists and references the cross-package boundary
test -f "${SUB}/AGENTS.md" || { echo "FAIL: missing AGENTS.md"; exit 1; }

# 2. pyproject.toml present and version-pinned
test -f "${SUB}/pyproject.toml"

# 3. Boundary lint passes
python scripts/ci/check_boundary.py "${SUB}"

# 4. Tests run (smoke)
cd "${SUB}" && pytest --collect-only -q
```

Run for every subproject. Anything that fails is added to the
Phase 1 deliverable backlog.

### 12.2 `[REMOVE]` Deprecated shims with deadlines

| Shim | Re-exports | Removal deadline | Trigger |
| --- | --- | --- | --- |
| `aqp/ml/` | `aqp_models.*` | End of Phase 1 (week 6) | All `aqp.ml.*` imports eradicated from `aqp/`, `aqp_bots/`, `aqp_rl/`, configs |
| `aqp/rl/` | `aqp_rl.*` | End of Phase 1 (week 6) | All `aqp.rl.*` imports eradicated |
| `aqp/llm/vllm_runner.py` | `aqp_models.serving.vllm` | End of Phase 1 | All `from aqp.llm.vllm_runner import *` replaced |
| `aqp/llm/ollama_client.py` | `aqp_models.serving.ollama` | End of Phase 1 | All `from aqp.llm.ollama_client import *` replaced |
| `aqp/api/routes/terraform.py` (HTTP broker) | `aqp_control_plane` Terraform routes | End of Phase 4 (week 18) | `AQP_TERRAFORM_USE_CONTROL_PLANE=true` is the default in prod |
| `webui/` (legacy Next.js 15) | `aqp_client/` | End of Phase 3 (week 14) | After Envoy cutover (Section 6.4 week 10) + 4-week soak |
| `aqp/ui/` (legacy Solara) | n/a | End of Phase 0 | Confirm no production env runs the `legacy` profile |
| `aqp/services/cluster_mgmt_client.py::ClusterMgmtClient` | `AQPControlPlaneClient` | End of Phase 4 | `AQP_CONTROL_PLANE_LEGACY_FALLBACK` defaults to false in prod |
| `aqp_platform/rollback/rpi_k8s_sdk/` | n/a | Kept indefinitely under `if rollback=true` workflow_dispatch only | n/a |

Each removal:
1. PR adds a `DeprecationWarning` with the removal deadline.
2. PR adds a CI lint failing any new import.
3. After the soak window, PR removes the module.
4. Final PR removes the lint.

### 12.3 `[ENHANCE]` Extraction-to-repo readiness checklist

When a subproject is ready to leave the monorepo as a standalone
repo, it must satisfy:

| Criterion | Pass condition |
| --- | --- |
| AGENTS.md | Present, references upstream boundaries |
| Boundary gate | CI lint passes |
| Test coverage | Unit + integration tests in CI |
| `pyproject.toml` | Self-contained; depends on published versions of upstream packages, not source paths |
| Versioning | Independent SemVer with Changeset |
| Documentation | Subproject docs live in `aqp_docs/docs/concepts/<area>/` and reference the subproject by published name |
| Deployment | Has its own Dockerfile + CI image build + Cosign signature |

Phase 4 closes Wave 1 (`aqp_platform_core`, `aqp_control_plane`,
`aqp_cli`, `aqp_admin`); Phase 6 closes Wave 2 (`aqp_rl`,
`aqp_models`, `aqp_bots`); Phase 8 closes Wave 3 (everything else).

---

## 13. Comprehensive FIX matrix

| Item | File / target | Phase |
| --- | --- | --- |
| Rule 6 — patched `0046` (lock + lint) | `alembic/versions/0046_workflow_versioning.py:175-198`, `alembic/versions/.hashes.lock` | 0 |
| Rule 26 — DataHub credentials | `aqp/data/datahub/client.py:35`, `aqp/data/datahub/aspect_puller.py:230`, `aqp/data/sources/alpha_vantage/datahub.py`, `aqp/tasks/visualization_tasks.py`, `aqp_platform/rollback/rpi_k8s_sdk/src/rpi_k8s_sdk/datahub.py` | 0 |
| Rule 29 — URN input | `aqp_client/src/routes/metadata/aspects/page.tsx:131-152,182-200` | 0 |
| Rule 22 — agent boundary (11 files) | `aqp/agents/strategy_memory.py`, `aqp/agents/analysis/reflector.py`, `aqp/agents/screening/llm_screener.py`, `aqp/agents/selection/annotation_writer.py`, `aqp/agents/tools/*.py` (8 files) | 0 |
| Rule 33 — regression test | `tests/api/test_metadata_aspect_cross_tenant.py` | 0 |
| Pydantic V1 sweep | `aqp/data/iceberg_catalog.py`, `aqp/data/airbyte/embedded.py`, plus any other `.dict(`/`.parse_obj(` hits | 0 |
| `print()` audit | All Python source outside `scripts/` | 0 |
| `\|\| true` masks | `.github/workflows/ci.yml:27,29`, `.github/workflows/security-scan.yml:68-69` | 1 |
| Unscoped Rule 33 regression test | `tests/api/test_metadata_aspect_cross_tenant.py` | 0 |

---

## 14. Comprehensive ENHANCE matrix

| Item | Target | Phase |
| --- | --- | --- |
| CI matrix per subproject | `.github/workflows/ci.yml` `test-subprojects` job | 1 |
| Cross-subproject boundary lint | `.github/workflows/ci.yml` matrix on `scripts/ci/check_boundary.py` | 1 |
| Per-subproject mypy strictness | `pyproject.toml` overrides per wave | 1 |
| Frontend coverage threshold | Vitest config in `aqp_client/`, `aqp_ui/` | 1 |
| Bandit scope expansion | `.github/workflows/security-scan.yml:58-77` | 1 |
| AGENTS Rule 6 procedure doc | `AGENTS.md` Rule 6 paragraph | 0 |
| Chainguard Wolfi base | All Dockerfiles | 2 |
| PSS restricted on every ns | `aqp_platform/deployments/kubernetes/**/namespace.yaml` | 2 |
| `aqp/auth/m2m.py` SPIFFE-backed | `aqp/auth/m2m.py` | 4 |
| OpenLineage outbox tip-hash anchors | `aqp/data/catalog/lineage.py` | 7 |
| Bipartite lineage v2 cell-aware | `aqp/lineage/graph/observer.py` | 7 |
| `BipartiteGraphObserver` writes `cell_id` | same | 7 |
| `aqp/data/iceberg_catalog.py::append_arrow` per-cell warehouse | same | 6 |
| `aqp/credentials/vault_transit.py` cell-aware | same | 6 |
| `aqp.persistence.db.SessionLocal` per-cell engine | `aqp/persistence/db.py` + `aqp/tenancy/factory.py` | 6 |
| `aqp/data/mcp/registry.py` emits `descriptor_hash` | same | 5 |
| `aqp/agents/runtime.py` records `mcp_tool_descriptor_hashes` | same | 5 |
| Kill-switch cross-cell fan-out | Phase 8 plumbing | 8 |
| `aqp_platform/configs/deployment/topology.yaml` `cells` section | same | 3 |
| `RequestContext` adds `cell_id`, `region`, `tenancy_strategy_alias` | `aqp/auth/context.py` | 3 |
| Per-cell K8s overlays | `aqp_platform/deployments/kubernetes/cells/<id>/` | 3 |
| Renovate config grouping | `renovate.json` | 1 |

---

## 15. Comprehensive ADD matrix

| Item | Target | Phase |
| --- | --- | --- |
| `.hashes.lock` | `alembic/versions/.hashes.lock` | 0 |
| Migration immutability lint | `scripts/ci/check_migration_immutability.py` | 0 |
| Migration chain lint | `scripts/ci/check_migration_chain.py` | 0 |
| Credential resolver lint | `scripts/ci/check_credential_resolver.py` | 0 |
| EntityPicker lint | `scripts/ci/check_entity_picker.py` | 0 |
| Agent boundary lint | `scripts/ci/check_agent_boundary.py` | 0 |
| Boundary lint generic | `scripts/ci/check_boundary.py` | 1 |
| DataHub credential store | `aqp/credentials/stores/datahub_credential_store.py` | 0 |
| Strategy memory MCP tool | `aqp/data/mcp/tools/strategy_memory.py` | 0 |
| Screening / annotation MCP tools | `aqp/data/mcp/tools/screening.py`, `aqp/data/mcp/tools/annotations.py` | 0 |
| Cache categories for metadata | `aqp/cache/keys.py::CACHE_CATEGORIES` | 0 |
| Cell registry migration | `alembic/versions/0081_cell_registry.py` | 3 |
| Audit cell_id column | `alembic/versions/0082_audit_cell_id_column.py` | 3 |
| MCP tool versioning migration | `alembic/versions/0083_mcp_tool_versioning.py` | 5 |
| Lineage cell_id migration | `alembic/versions/0084_lineage_cell_id.py` | 7 |
| Cosign keyless sign job | `.github/workflows/build-multi-arch.yml` | 2 |
| Syft SBOM + Cosign attest | same | 2 |
| Grype scan gate | same | 2 |
| Kyverno cluster policies | `aqp_platform/deployments/kubernetes/security/kyverno/` | 2 |
| `aqp-edge` Envoy image | `aqp_platform/build/docker/aqp-edge/Dockerfile` | 3 |
| `aqp-tenant-router` service | `aqp_platform/build/docker/aqp-tenant-router/` | 3 |
| `/manage/cells/*` routes | `aqp_control_plane/src/aqp_cp/api/routers/cells.py` | 3 |
| Argo CD ApplicationSet over cells | `aqp_platform/deployments/argocd/cells-appset.yaml` | 3 |
| Linkerd 2.16 per cell | `aqp_platform/deployments/kubernetes/cells/<id>/linkerd/` | 4 |
| SPIRE Server + Agent | same | 4 |
| Cedar policy engine | `aqp/api/security_cedar.py`, `aqp_platform/configs/cedar/policies/*.cedar` | 4 |
| Pomerium IAP for `/manage/*` | `aqp_platform/deployments/kubernetes/cells/<id>/pomerium/` | 4 |
| `vault-secrets-operator` | `aqp_platform/deployments/kubernetes/cells/<id>/vault-operator/` | 4 |
| Per-tenant MCP routing | `aqp/data/mcp/tenant_router.py` | 5 |
| Per-tenant MCP K8s manifests | `aqp_platform/deployments/kubernetes/cells/<id>/mcp-tenants/` | 5 |
| Biscuit capability tokens | `aqp/auth/biscuit.py` | 5 |
| gVisor RuntimeClass | `aqp_platform/deployments/kubernetes/cluster/gvisor-runtimeclass.yaml` | 5 |
| `Cell-Bound-Authorization` validation | `aqp-edge` Envoy config | 5 |
| Per-cell CNPG cluster CRD | `aqp_platform/deployments/kubernetes/cells/<id>/postgres/` | 6 |
| Per-cell Redis Helm values | same | 6 |
| Per-cell MinIO/S3 with Object Lock | same | 6 |
| Per-cell MLflow tracking server | same | 6 |
| Per-cell Iceberg REST catalog | same | 6 |
| Dual-write backfill script | `scripts/cells/dual_write_backfill.py` | 6 |
| Audit lake hourly flush | `aqp/tasks/audit_lake_tasks.py` | 7 |
| Transparency anchor sinks | `aqp/audit/anchors/rekor.py`, `qldb.py`, `tsa.py` | 7 |
| Replay harness | `aqp/audit/replay.py` | 7 |
| Evidence bundle endpoint | `aqp_control_plane/src/aqp_cp/api/routers/evidence.py` | 7 |
| Cell drain endpoint | `aqp_control_plane/src/aqp_cp/api/routers/cells.py` | 8 |
| Cross-region CNPG replication | `aqp_platform/deployments/kubernetes/cells/<id>/postgres/replica.yaml` | 8 |
| DR drill script | `scripts/dr/run_failover_drill.py` | 8 |
| Killswitch cross-cell SLO test | `tests/dr/test_killswitch_cross_cell.py` | 8 |
| SPIFFE workload identity docs | `aqp_docs/docs/concepts/identity/spiffe-workload-identity.md` | 4 |
| Cell-topology docs | `aqp_docs/docs/concepts/platform/cell-topology.md` | 3 |
| Cell-migration runbook | `aqp_docs/docs/how-to/operations/cell-migration.md` | 6 |
| Evidence-bundle runbook | `aqp_docs/docs/how-to/operations/evidence-bundle-export.md` | 7 |
| DR drill runbook | `aqp_docs/docs/how-to/operations/dr-drill.md` | 8 |

---

## 16. Comprehensive REMOVE matrix

| Item | Reason | Trigger / phase |
| --- | --- | --- |
| `aqp/ml/` shim | `aqp_models` is the canonical home | Phase 1 |
| `aqp/rl/` shim | `aqp_rl` is the canonical home | Phase 1 |
| `aqp/llm/vllm_runner.py` shim | Moved to `aqp_models.serving.vllm` | Phase 1 |
| `aqp/llm/ollama_client.py` shim | Moved to `aqp_models.serving.ollama` | Phase 1 |
| `aqp/api/routes/terraform.py` HTTP broker | Control-plane owns Terraform (Rule 42) | Phase 4 |
| `aqp/services/cluster_mgmt_client.py::ClusterMgmtClient` | Rollback-only; replaced by `AQPControlPlaneClient` | Phase 4 |
| `webui/` (legacy Next.js 15) | `aqp_client/` is the canonical client per `CUTOVER.md` | Phase 3 |
| `aqp/ui/` (legacy Solara) | Unused except behind `legacy` profile | Phase 0 |
| `\|\| true` masks in CI | Silently hides lint failures | Phase 1 |
| Python FastAPI cell proxy | Replaced by Envoy `aqp-edge` | Phase 3 |
| Inline `os.environ` / `os.getenv` reads outside `aqp/config/settings.py` | Rule 7 enforcement | Phase 0 |
| Free-text URN inputs in frontend | Rule 29 enforcement | Phase 0 |
| Defensive comment block at `alembic/versions/0046_workflow_versioning.py:175-198` | Replaced by `.hashes.lock` as source of truth | Phase 0 |
| "Grandfathered" comment at `aqp/data/datahub/aspect_puller.py:225-228` | Refactored to `CredentialResolver` | Phase 0 |
| Direct `settings.<svc>_token` reads | Rule 26 enforcement | Phase 0 |
| Direct `redis.publish` outside `aqp/tasks/_progress.py` / `aqp/ws/` / `aqp/cache/` | Rule 4 enforcement | Phase 1 |
| Direct `redis_client.ft(...)` outside `aqp/rag/` | Rule 11 enforcement | Phase 1 |
| Hardcoded `*-service.svc.cluster.local` URLs | Rule 47 enforcement | Phase 1 |
| Direct `engine.connect()` for org-scoped queries | Rule 51 enforcement | Phase 1 |
| Direct `agent.train(...)` from outside `RLRuntime` | Rule 16 (already enforced — add static check) | Phase 1 |

---

## 17. Risks, caveats, open decisions

### 17.1 Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Per-cell Postgres migration fails halfway | High | Three-phase dual-write with read-cut last; `AQP_CELL_DUAL_WRITE` feature flag; rollback path via reverting the flag |
| Cell router introduces a 5-15ms hop on every request | Medium | Envoy in HTTP-only mode keeps the proxy cost ~1ms; measure with `linkerd-viz` before/after |
| SPIFFE adoption breaks existing M2M tokens | Medium | `IdentityProviderMeta` registry supports parallel providers; SPIFFE rolled out per cell with the JWT path remaining for cross-cell |
| Cedar policy regressions cause `/manage/*` outages | Medium | Cedar evaluated alongside resource filter for 4 weeks before resource filter is removed for `/manage/*` routes; canary policies |
| Kyverno signature verify blocks legitimate hotfix images | Medium | Operator emergency override via Kyverno `validationFailureAction: Audit` for a 1-hour window |
| Transparency-log dependency causes hourly audit-lake flush to fail | Low | Anchor sinks are append-only and retry indempotently; failures escalate but don't block the Postgres hot path |
| gVisor performance penalty on agent-sandbox workloads | Low | Benchmark before/after; if penalty > 30%, switch to Kata or hardware MicroVM for the hot agent path |
| Per-cell MinIO/Iceberg increases storage cost N× | Medium | `silo-reg` tenants pay for the isolation; `shared-std`/`shared-prem` share storage backplane until tier compliance demands separation |

### 17.2 Open decisions

| Decision | Owner | Deadline |
| --- | --- | --- |
| CNPG vs Aurora-per-cell for the AWS-native deployment | Platform | Pre-Phase 6 (week 14) |
| Rekor vs QLDB vs RFC 3161 TSA for transparency anchor | Compliance | Pre-Phase 7 (week 18) |
| Linkerd vs Cilium service mesh | Platform | Pre-Phase 4 (week 10) — currently Linkerd is the recommendation |
| Per-cell Kafka/Redpanda or stick with global | Platform | Deferred to first `silo-reg` tenant request |
| Theia 1.72 → 1.78+ for `aqp_ide` | Platform | Track upstream; not blocking |
| gVisor vs Kata vs Firecracker for agent sandbox | Security | Pre-Phase 5 (week 12) |
| Cedar vs OPA-as-application-authz | Security | Section 7.3 recommends Cedar — confirm by week 10 |
| Pomerium vs Authelia vs custom for IAP | Security | Section 7.5 recommends Pomerium — confirm by week 10 |
| Are tenant migrations always cross-cell-allowed? | Compliance | `silo-reg` tenants pinned by default; need policy doc |

### 17.3 Caveats

- **Blueprint's `0050_fix_0048.py` / `0051_fix_0049.py` is wrong** —
  those revision IDs are taken (`0050_terraform_iac_plus_entra.py`,
  `0051_seed_wiley_tech.py`). Section 3.1 explains the
  hash-lock-from-current-state alternative.
- **The audit's `frontend/src/routes/metadata/aspects/page.tsx`
  path no longer exists** — moved to `aqp_client/src/routes/metadata/aspects/page.tsx`.
- **Rule 33 is closed in code** at
  `aqp/data/mcp/tools/aspects.py:771-777` but the regression test
  is missing.
- **`tests/` is not being run by the existing CI pipelines** —
  there is no CI step running the master pytest suite at
  `tests/`. This is the single biggest existing-state risk; the
  Phase 1 matrix only adds per-subproject jobs and does not cover
  the legacy `tests/` folder.
- The 8 audit findings under `pyproject.toml` Pydantic V1 are
  unknown-state — Phase 0.5 must regrep.

---

## 18. Recommendations and triggers

### 18.1 Sequence priorities

1. **Phase 0 ships first** (weeks 1–2). Nothing in Phases 1–8 makes
   sense until the audit gates exist; otherwise the same class of
   violation walks right back in.
2. **Phases 1 + 2 in parallel** (weeks 2–10). CI and supply chain
   are independent.
3. **Phase 3 cell topology** is the architectural pivot. Don't
   start Phases 4–8 until Phase 3 has the cell registry live and
   `RequestContext.cell_id` propagating.
4. **Phases 4 + 5 in parallel** once Phase 3 lands.
5. **Phase 6 data-plane silo** is the most invasive — start the
   dual-write windows late but plan early.
6. **Phase 7 audit immutability** can start in parallel with
   Phase 6 since it's additive to existing Postgres tables.
7. **Phase 8 multi-region** is the last because every preceding
   phase has to be cell-clean first.

### 18.2 Stop conditions

Halt the plan and re-plan if:
- The Phase 0 audit lints land but produce > 100 violations in the
  existing tree (suggests the rules need redrawing rather than
  enforcement).
- Phase 3's cell registry latency exceeds 5ms on the hot path
  (cell router becomes a bottleneck).
- Phase 6's dual-write window cannot complete within 30 days for a
  `shared-std` cell (suggests the backfill plumbing is wrong).
- Any phase introduces a regression in the kill-switch p99 SLO.

### 18.3 Documentation hygiene

Every phase produces a runbook in
`aqp_docs/docs/how-to/operations/`:
- `migration-immutability-lock.md` (Phase 0)
- `entitypicker-rollout.md` (Phase 0)
- `subproject-extraction-checklist.md` (Phase 1)
- `chainguard-base-migration.md` (Phase 2)
- `cell-router-cutover.md` (Phase 3)
- `linkerd-spire-rollout.md` (Phase 4)
- `per-tenant-mcp-rollout.md` (Phase 5)
- `cell-data-plane-migration.md` (Phase 6)
- `audit-lake-replay.md` (Phase 7)
- `cell-drain-and-failover.md` (Phase 8)

Each runbook lives under the `aqp_docs/` boundary (Rule "canonical
docs", AGENTS.md `aqp_docs/` row), is referenced from the master
`AGENTS.md`, and links back to this plan.

---

## 19. Section index

| § | Title | Lines |
| --- | --- | --- |
| 1 | Audit reality check | Top |
| 2 | Current architecture snapshot | After §1 |
| 3 | Phase 0 — Audit closure | Weeks 1–2 |
| 4 | Phase 1 — CI/CD hardening | Weeks 2–6 |
| 5 | Phase 2 — Container & supply chain | Weeks 4–10 |
| 6 | Phase 3 — Cell topology | Weeks 6–14 |
| 7 | Phase 4 — Service mesh & identity | Weeks 10–18 |
| 8 | Phase 5 — Per-tenant MCP & agent sandbox | Weeks 12–20 |
| 9 | Phase 6 — Data plane silo per cell | Weeks 16–24 |
| 10 | Phase 7 — Audit immutability & reconstruction | Weeks 18–26 |
| 11 | Phase 8 — Multi-region & DR | Weeks 24–36 |
| 12 | Repository split finalization | Parallel |
| 13 | Comprehensive FIX matrix | — |
| 14 | Comprehensive ENHANCE matrix | — |
| 15 | Comprehensive ADD matrix | — |
| 16 | Comprehensive REMOVE matrix | — |
| 17 | Risks, caveats, open decisions | — |
| 18 | Recommendations and triggers | — |
| 19 | This index | — |

---

**Plan version**: 1.0 (drafted against repo state at Alembic head
`0080`, AGENTS.md hard-rules 1–55, May 2026 audit).

**Next action**: open the Phase 0 PR series. The first PR is
`scripts/ci/check_migration_immutability.py` + `.hashes.lock` (the
single highest-leverage change in the entire plan).


