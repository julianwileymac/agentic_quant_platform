# WORKFLOW.md

> Human ↔ Cursor-agent collaboration cadence for AQP.
> Pair with [AGENTS.md](AGENTS.md) (the AI rule-set),
> [CONTRIBUTING.md](CONTRIBUTING.md) (human onboarding),
> and [aqp_docs/docs/concepts/agentic/agentic-development.md](aqp_docs/docs/concepts/agentic/agentic-development.md)
> (how AQP's spec-pattern relates to the broader agentic-coder
> vocabulary).

## Why this file exists

[AGENTS.md](AGENTS.md) tells the AI **what** the rules are.
[CONTRIBUTING.md](CONTRIBUTING.md) tells humans **how to set up** the
project. Neither codifies **how the human + the Cursor agent
collaborate** — when to plan, when to execute, when to halt, how to
calibrate velocity, when human approval is non-bypassable. That's
this file.

## The three-phase loop

Every non-trivial change runs through three explicit phases. The
phases must not be combined into one prompt: mixing them makes the
agent drift from requirements and ship technical debt.

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│  PLAN    │ →  │   ACT    │ →  │ REFLECT  │
└──────────┘    └──────────┘    └──────────┘
   (spec)        (execute)       (capture +
                                   doc-update)
```

### 1. Plan

- Use **Cursor's plan mode** (or "Ask Mode" in older builds) for
  this phase. The agent is read-only here — it cannot modify files.
- Output is a markdown plan with cited file paths and code snippets.
  Cursor stores plans in the workspace state at
  `<workspace>/.cursor/plans/` (not in this repo) — the agent and
  the human work from the same plan file.
- The human reviews the plan before approving. Clarifying questions
  are asked **one or two at a time**, not as a long survey.
- Do **not** start coding during this phase. If the agent generates
  implementation code in plan mode, that's a bug — back out and
  re-prompt.

### 2. Act

- After the plan is approved, switch to agent mode.
- The agent executes the plan one task at a time, marking each
  todo item `in_progress` → `completed`.
- For SLOW-mode work (see below), the agent must follow the TDD
  loop: write the failing test, run it to confirm it fails, then
  implement to green, then refactor.
- Long-running operations (backtests, data ingestion, training,
  Docker stack rebuild) can run in **Background Mode** so the
  primary chat stays responsive.

### 3. Reflect

- After the change lands, the agent must update any documentation
  / ERD / data-dictionary entries the change implies. The
  scoped `.cursor/rules/*.mdc` files require this for migrations
  ([migrations-persistence.mdc](.cursor/rules/migrations-persistence.mdc))
  and for new ORM models.
- Capture the lessons learned in
  [.agents/state-template.md](.agents/state-template.md) **only if**
  the work spans multiple sessions — otherwise the chat history
  + the PR description are enough.
- Do **not** create empty-summary commits or "session retrospective"
  docs proactively. Brevity wins.

## Velocity calibration: FAST vs SLOW

Different surfaces demand different rigor. The agent must explicitly
operate in one of two modes for any non-trivial change.

### FAST mode

For exploratory research that does **not** touch live capital paths,
the audit ledger, or the immutable spec versions:

- Notebook prototyping in [notebooks/](notebooks/)
- Ad-hoc data-quality experiments in `aqp/ml/adhoc/`
- New `aqp.ml.flows.run_<flow>_flow(...)` workbench flows
- New analysis flows registered via
  [`@register_analysis_flow`](aqp/analysis/registry.py) (the runtime
  enforces audit + immutability for free, so they're FAST-eligible)
- Dashboard / visualisation tweaks
- New chart-pattern detectors
  ([aqp/data/patterns.py](aqp/data/patterns.py))
- Indicator zoo additions
  ([aqp/data/indicators_zoo.py](aqp/data/indicators_zoo.py))
- New strategy YAML configs that compose existing components

FAST mode skips strict TDD-loop. It still respects:

- The cardinal rules in [.cursor/rules/aqp.mdc](.cursor/rules/aqp.mdc)
- Linting + formatting (`ruff check`, `ruff format`)
- Hermetic test conventions (no real network / filesystem in tests)

### SLOW mode

Mandatory TDD-loop and explicit human approval before commit. SLOW
applies to anything in:

- [aqp/risk/](aqp/risk/) — kill-switch, position limits, drawdown
  guards
- [aqp/persistence/ledger.py](aqp/persistence/ledger.py) — the
  single ledger entry-point
- [aqp/trading/](aqp/trading/) — live + paper trading session loop,
  brokerages, feeds
- Any `*_runtime.py` under
  `aqp/{agents,bots,rl,analysis}/runtime.py` — telemetry +
  immutable-version invariants live here
- [alembic/versions/](alembic/versions/) — schema migrations
- [aqp/llm/providers/router.py](aqp/llm/providers/router.py) — the
  single LLM entry-point
- [aqp/data/iceberg_catalog.py](aqp/data/iceberg_catalog.py) — the
  single Iceberg-write entry-point
- The progress-bus contract
  ([aqp/tasks/_progress.py](aqp/tasks/_progress.py))
- Anything covered by an `alwaysApply: true` rule

SLOW-mode TDD loop:

1. Write failing tests that pin the new behaviour (input → expected
   output, edge cases, invariants).
2. Run the tests; confirm they fail for the right reason.
3. Pause for human review of the test suite.
4. Implement to green, **without** modifying the original assertions
   except to fix a typo or strengthen the invariant.
5. Run lint + format. Run the impacted test directory. Pause for
   human approval before commit.

## Intervention nodes (un-bypassable human authorization)

The agent must **stop and ask** before doing any of the following.
There is no "FAST mode override" for these.

| Intervention node | Why |
| --- | --- |
| **Kill-switch flips** ([aqp/risk/kill_switch.py](aqp/risk/kill_switch.py), `POST /portfolio/kill_switch`) | Halts every paper / live session — confirm intent |
| **Broker API credentials** | Read or write of any `AQP_*_API_KEY` env var, or any change to [aqp/utils/keys.py](aqp/utils/keys.py) helpers |
| **Alembic migrations** | Schema is shared state across all environments; review the autogenerated file before applying |
| **Spec re-snapshots that change behaviour** | A new `agent_spec_versions` / `bot_versions` / `rl_experiment_versions` / `analysis_spec_versions` row affects ledger replay semantics |
| **Force-push to `main`** | Forbidden outside an explicit human-approved recovery |
| **Live (not paper) trading writes** | Anything in [aqp/trading/brokerages/](aqp/trading/brokerages/) that hits a non-sandbox broker URL |
| **Bulk Iceberg consolidation / table drop** | The [aqp/data/iceberg_consolidate.py](aqp/data/iceberg_consolidate.py) `confirm` flag exists for this — never auto-confirm |
| **`agent_spec_versions` / `bot_versions` / `rl_experiment_versions` / `analysis_spec_versions` row deletion** | Those rows are **immutable** — deleting one breaks the audit chain |
| **Production-only environment variables** | Anything affecting Cloudflare tunnel egress, the rpi_kubernetes cluster, or the host warehouse on `C:/aqp-warehouse` |

When the agent encounters one of these, it must surface a clear
intent statement and wait for explicit human acknowledgement before
proceeding.

## FREEMODE

For brainstorming about quantitative ideas, market regimes, paper
authoring, or general design discussion, the human can wrap a chat
exchange in `FREEMODE START` / `FREEMODE END` markers:

```
FREEMODE START
... unstructured discussion ...
FREEMODE END
```

Inside this block:

- The agent must **not** modify code or state files.
- The agent must **not** update todo lists.
- The agent must **not** dispatch subagents to implement anything.
- The agent should treat the discussion as exploration, not
  requirements gathering.

When the human writes `FREEMODE END`, the conversation returns to
normal cadence — at which point the human will explicitly say what
(if anything) from the discussion should be turned into a plan.

## Working with subagents

For genuinely independent exploration or review work — not for
"this big task should run in a subagent so it doesn't pollute my
chat":

- Read-only exploration of an unfamiliar subsystem → `explore`
  subagent
- Long-running implementation that benefits from isolation → use a
  `best-of-n-runner` subagent in a worktree (still requires human
  review before merge)
- Critique of a proposed conventions / rules change →
  [.cursor/agents/aqp-rules-reviewer.md](.cursor/agents/aqp-rules-reviewer.md)

Subagent results must be reviewed by the parent agent and the human
before being applied. A subagent's output is a recommendation, not a
finished change.

## Cross-references

- [AGENTS.md](AGENTS.md) — the canonical 45 hard rules
- [CONTRIBUTING.md](CONTRIBUTING.md) — human dev-environment
  onboarding
- [.cursor/rules/](.cursor/rules/) — glob-scoped rule files
- [.agents/state-template.md](.agents/state-template.md) —
  cross-session state schema
- [aqp_docs/docs/concepts/agentic/agentic-development.md](aqp_docs/docs/concepts/agentic/agentic-development.md) —
  spec-pattern as the AQP skill-artifact equivalent + the ADLC
  security manifesto
- [aqp_docs/docs/concepts/agentic/multi-agent-patterns.md](aqp_docs/docs/concepts/agentic/multi-agent-patterns.md) —
  Sequential / Parallel / Debate / ReAct / Coordinator patterns
  mapped to [aqp/agents/graph/](aqp/agents/graph/)
