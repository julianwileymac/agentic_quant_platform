# Agentic development for AQP

> The single doc that connects AQP's existing primitives to the
> broader "agentic-coder" vocabulary, plus the consolidated security
> manifesto. Doc map: [docs/index.md](index.md) ·
> Workflow: [../WORKFLOW.md](../WORKFLOW.md) ·
> Hard rules: [../AGENTS.md](../AGENTS.md).

## What this doc is for

The agentic-coder research literature talks about
"skill artifacts", "skill graphs", "Memento-skills", "auditable
execution trails", and "MCP control planes" as if they were novel
patterns to invent. AQP already implements every one of them — under
different names, with stronger invariants, and with ledger-backed
audit chains. This doc makes that mapping explicit so you don't waste
time inventing a parallel "skill" surface alongside the four spec
runtimes that already exist.

The doc has three sections:

1. **AQP's spec-pattern is the skill-artifact pattern.** The
   four-runtime architecture (Agent / Bot / RL / Analysis) is the
   skill-graph + Memento-skill equivalent. Including where AQP
   deliberately diverges from research recommendations.
2. **Working with Cursor agents in AQP.** Static channel + dynamic
   channel + plan-mode vs agent-mode usage.
3. **The ADLC security manifesto.** Consolidated for the first time.

## 1. The spec-pattern is the skill-artifact pattern

### The four spec runtimes

| Spec | Runtime | Versions table | Canonical doc |
| --- | --- | --- | --- |
| [`AgentSpec`](../aqp/agents/spec.py) | [`AgentRuntime`](../aqp/agents/runtime.py) | `agent_spec_versions` | [agents.md](agents.md) |
| [`BotSpec`](../aqp/bots/spec.py) | [`BotRuntime`](../aqp/bots/runtime.py) | `bot_versions` | [bots.md](bots.md) |
| [`RLExperimentSpec`](../aqp/rl/spec.py) | [`RLRuntime`](../aqp/rl/runtime.py) | `rl_experiment_versions` | [rl-framework.md](rl-framework.md) |
| [`AnalysisSpec`](../aqp/analysis/spec.py) | [`AnalysisRuntime`](../aqp/analysis/runtime.py) | `analysis_spec_versions` | [analysis-framework.md](analysis-framework.md) |

Each is:

- **Declarative** — a Pydantic model with strict types.
- **Hash-locked** — the SHA-256 of the canonical-JSON-serialized
  spec is the version key.
- **Auto-versioned** — first run snapshots a row in the `*_versions`
  table; behaviour changes produce new rows; old rows are immutable.
- **Ledger-backed** — every run records `spec_version_id` so the
  exact run can be deterministically replayed against historical
  data.
- **Discoverable** — the registry pattern (built-ins + YAML
  auto-loading) means new specs come online without touching the
  runtime.

### Mapping to research vocabulary

The agentic-coder literature 2024–2026 used several overlapping terms.
Here's how each lands on AQP's primitives:

| Research term | AQP equivalent | Notes |
| --- | --- | --- |
| "Skill artifact" | One row in a `*_versions` table | The artifact has semantic interface (the Pydantic spec), preconditions (the spec's input schema), executable payload (the runtime invocation), and deterministic postconditions (the run row + Iceberg outputs). |
| "Skill graph" | The full registry across the four runtimes | Each runtime hosts one graph; `BotSpec` references `AgentSpec`s, `RLExperimentSpec` references data pipelines, `AnalysisSpec` references flows. |
| "Auditable execution trail" | `*_runs` ledger rows + Iceberg outputs + per-step result tables | E.g. `analysis_runs` + `analysis_step_results` + `aqp_gold_analysis_<flow.namespace>` |
| "MCP control plane" | The DataMCPTool catalog | One catalog, two transports (in-process bridge + FastAPI router + stdio binary). See [data-mcp.md](data-mcp.md). |
| "Memento-skill / continual learning" | Re-snapshot on change | When a spec changes, `persist_spec` inserts a **new** version row — old versions stay for replay. The "memory" is the immutable history. |
| "Verifiable rewards" | The `*_runs` ledger + cost caps + guardrails on the runtime | Telemetry covers cost, latency, and outcome metrics. |

### Where AQP **deliberately diverges**

The research recommends some patterns that AQP rejects on purpose:

1. **"Rewrite the skill on failure" / self-modifying skills.** The
   research literature (e.g. *new framework lets AI agents rewrite
   their own skills without retraining*) advocates patching a
   failing skill in-place. **AQP forbids this.** Reasons:
   - Auditability — every behaviour change must be a new
     hash-locked version row, not an in-place mutation.
   - Replay — runs reference `spec_version_id` for replay; mutating
     the spec breaks the replay invariant.
   - Compliance — financial systems need an append-only audit
     trail.
   - Risk — a self-mutating spec next to live capital is a
     non-starter.
   The right pattern in AQP: when a spec fails, author a new
   spec version (manually or via tooling), snapshot it, switch
   traffic. The previous version remains for forensics.
2. **"Skill graph self-improvement loops"** that mutate skill
   metadata across runs. AQP's metadata is owned by the active
   metadata layer
   ([`aqp.data.catalog.register_dataset`](../aqp/data/catalog/active_metadata.py))
   and updated through explicit upserts — never as a side effect
   of a run.
3. **"Free-form SQL tools for agents"** to "let the model figure it
   out". AQP requires every read to go through a registered
   `DataMCPTool` with a strict args schema and policy check. See
   [data-mcp.md](data-mcp.md) and the
   [data-mcp.mdc](../.cursor/rules/data-mcp.mdc) Cursor rule.
4. **"Auto-update implementation when intent changes"** (intent-driven
   development with bidirectional updates). AQP's docs are
   updated in the same PR that touches the code, by humans or
   under explicit human review. Drift detection is welcome;
   automatic mutation is not.

### Adding a new spec — the canonical flow

1. Pick the right runtime by the question being answered:
   - "What should an LLM-driven agent do?" → `AgentSpec`
   - "What should a deployable bot (universe + strategy + risk +
     ML + agents + RAG) do?" → `BotSpec`
   - "What should an RL experiment train / evaluate?" →
     `RLExperimentSpec`
   - "What statistical / numerical analysis flow should run on a
     dataset?" → `AnalysisSpec`
2. Author the YAML or programmatic Pydantic instance.
3. Call the right `persist_spec(...)` (or let the registry do it
   on first lookup).
4. Run via the runtime — the first run snapshots a `*_versions`
   row.
5. The run row records `spec_version_id` and emits progress through
   [`aqp/tasks/_progress.py`](../aqp/tasks/_progress.py).

If you find yourself wanting to "add a new skill artifact" outside
this pattern — stop, read this section again, pick the right spec
runtime.

## 2. Working with Cursor agents in AQP

### The two-channel context strategy

AQP follows the static / dynamic context bifurcation pattern that
Anthropic's Cursor integration recommends:

- **Static channel** — what doesn't change between sessions:
  - [AGENTS.md](../AGENTS.md) — 25 hard rules
  - [.cursor/rules/](../.cursor/rules) — glob-scoped rule files
  - [docs/](../docs) — narrative architecture
- **Dynamic channel** — what changes session-to-session:
  - DataMCPTool catalog (live database schemas, dataset lineage,
    entity catalog)
  - The `agent_runs_v2` / `bot_deployments` / `rl_runs` /
    `analysis_runs` ledger rows
  - The Cursor environment's recently-edited / open files /
    terminal state

The Cursor agent should treat the static channel as authoritative
for **rules and architecture**, and the dynamic channel as
authoritative for **live state** (don't guess a table schema —
query the MCP catalog).

### Plan mode vs agent mode

| Mode | When | Restrictions |
| --- | --- | --- |
| **Plan mode** | Complex / ambiguous tasks, architectural decisions, large refactors, anything with > 1 valid implementation | Read-only — cannot edit files |
| **Agent mode** | Single clear task, post-plan implementation, debugging once root cause is known | Full tool access |
| **Background mode** | Long-running tasks (Docker stack rebuild, full test suite, training runs) | Runs in parallel; non-blocking |
| **Ask mode** | "How does X work?" / read-only exploration | Cannot edit; can search |

The
[../WORKFLOW.md](../WORKFLOW.md) document has the full plan→act→reflect
cadence including FAST vs SLOW velocity calibration and intervention
nodes.

### Reading the agent's plan output as a structured spec

When Cursor's plan mode produces a `.cursor/plans/*.plan.md` file,
treat it like a `*Spec` artifact: the human reviews, approves, and
the agent then executes the plan one task at a time, updating todos
as it goes. The plan file is the contract.

## 3. ADLC security manifesto

The Agentic Development Life Cycle (ADLC) framing says: as agentic
autonomy expands, the security posture must scale with it. AQP
already enforces several layers; this section consolidates them
in one place so you can audit the surface in one read.

### Layer 1 — Kill-switch (ultimate human override)

- Code: [aqp/risk/kill_switch.py](../aqp/risk/kill_switch.py),
  [aqp/risk/manager.py](../aqp/risk/manager.py)
- Wired endpoint today: `POST /portfolio/kill_switch` in
  [aqp/api/routes/portfolio.py](../aqp/api/routes/portfolio.py)
- Frontend topbar component:
  [frontend/src/components/common/KillSwitch.tsx](../frontend/src/components/common/KillSwitch.tsx)
- Design contract for per-runtime fan-out — `/agents/halt`,
  `/paper/stop-all`, `/bots/halt-all`, `/rl/halt-all` — see
  [frontend.mdc](../.cursor/rules/frontend.mdc) (wire as the
  endpoints come online; add them to `KillSwitch` in the same PR).
- All paper sessions halt within one heartbeat and cancel open
  orders. The Meta-Agent can flip the switch; an operator can flip
  it; the agent is never allowed to flip it without explicit human
  acknowledgement (per
  [WORKFLOW.md](../WORKFLOW.md)#intervention-nodes).

### Layer 2 — Immutable spec versions (audit trail)

- `agent_spec_versions`, `bot_versions`, `rl_experiment_versions`,
  `analysis_spec_versions` are append-only.
- Each spec is hash-locked (SHA-256 of canonical JSON).
- Every run records `spec_version_id` for replay.
- This guarantees: **every behaviour change has a permanent record**
  identifying who introduced it (via the commit) and what the spec
  looked like at that moment.

### Layer 3 — DataMCPTool boundary (no direct catalog reads)

- Agents MUST NOT `import aqp.persistence.models...` or call
  `iceberg_catalog` / `duckdb_provider` directly inside their body.
- All reads go through registered `DataMCPTool`s, exposed via
  in-process bridge + FastAPI `/mcp/data` router + `aqp-data-mcp`
  stdio binary.
- See [data-mcp.md](data-mcp.md) and
  [data-mcp.mdc](../.cursor/rules/data-mcp.mdc).

### Layer 4 — Single LLM entry-point (router_complete)

- All LLM calls go through
  [`router_complete`](../aqp/llm/providers/router.py).
- No direct `litellm.completion` / `OllamaClient` / vendor SDKs.
- The router enforces tier policies, cost caps, and provider
  fallback. Bypassing it strips those guardrails.

### Layer 5 — Single Iceberg entry-point + medallion enforcement

- All writes go through
  [`iceberg_catalog.append_arrow`](../aqp/data/iceberg_catalog.py)
  / `create_or_replace_table`.
- The wrapper validates that the namespace prefix matches the
  declared `medallion_layer` (`bronze` / `silver` / `gold`).
- `BusinessMetadata` is mandatory on first write — agents query
  this surface to know what a dataset is for.
- See [data-layer-unification.md](data-layer-unification.md) and
  [iceberg.mdc](../.cursor/rules/iceberg.mdc).

### Layer 6 — Secrets and configuration

- Configuration through
  [`aqp.config.settings`](../aqp/config/__init__.py) only — never
  construct a fresh `Settings()`, never read `os.environ` directly.
- New env vars are `AQP_*`-prefixed fields on the `Settings` class
  in [aqp/config/settings.py](../aqp/config/settings.py) and added
  to [.env.example](../.env.example).
- Credentials use the helpers in
  [aqp/utils/keys.py](../aqp/utils/keys.py); never paste them
  into `.env` outside what's already in `.env.example`.

### Layer 7 — Migration immutability

- See [migrations-persistence.mdc](../.cursor/rules/migrations-persistence.mdc).
- Shipped migrations are never edited. Schema bugs are fixed
  forward, never backward.

### Layer 8 — Pre-merge checklist (human-driven)

The checklist in [CONTRIBUTING.md](../CONTRIBUTING.md) is the last
line of defence:

- Tests pass locally
- Docs updated (data-dictionary, ERD, glossary)
- New env vars in `.env.example`
- New deps in `pyproject.toml`
- Migration applied + reviewed (autogenerate footguns checked)
- For SLOW-mode work: TDD-loop followed (see
  [WORKFLOW.md](../WORKFLOW.md))

### Recommended (not yet enforced) — red-team review

For any new `AgentSpec` that gains broker-API or live-trading
tools, run a red-team review before promoting from paper to live:

- Adversarial prompt simulation
- Boundary-violation tests (does the agent try to escape its
  tool catalog?)
- Cost-cap stress (does it loop?)
- Margin / risk-limit interaction (does the spec respect
  [aqp/risk/](../aqp/risk/) constraints?)

Today this is documentation, not automation. Future work: a
`POST /agents/red-team-review` task that takes an `AgentSpec` and
runs a fixed adversarial battery against it before promotion.

## When in doubt

1. Read [../AGENTS.md](../AGENTS.md) — the canonical 25 rules.
2. Read [../WORKFLOW.md](../WORKFLOW.md) — the cadence.
3. Read [multi-agent-patterns.md](multi-agent-patterns.md) — when
   you're scaling the agent topology.
4. Read [glossary.md](glossary.md) — for terminology.
5. Search the code: `rg "<symbol>" aqp/`.
