# aqp_index

Single-source-of-truth index for the AQP monorepo.

## What lives here

Curated, deduplicated pointers into:

- The project's centralized index (top-level map of every aqp_* package).
- Architecture documentation (SSoT: one canonical location per concept,
  with backlinks to richer prose in [aqp_docs/](../aqp_docs/)).
- Configuration sets (consolidated, env-overlay-aware view of every
  important configuration knob).
- Code indices (per-module function/class signatures designed to reduce
  agent token consumption when navigating large packages).
- The project skills registry and the documents that explain how to add,
  extend, and maintain skills.
- The subagent registry and extension guidance.

## Invariant

**Only the [aqp-index-curator](../.cursor/agents/aqp-index-curator.md)
subagent writes to this tree.** Other agents and humans read it.

This rule exists because:

1. The index's only value is that it stays in sync with reality. A
   single writer with a strict refresh discipline is the cheapest way
   to keep it honest.
2. Duplicating canonical text invites drift. The curator only writes
   pointers + summaries + cited signatures.
3. Token budgets are real. The curator owns the methodology and
   maintains it explicitly under [code-index/](code-index/).

Humans who notice staleness should file a note in
[.cursor/plans/](../.cursor/plans/) and let the curator pick it up.

## Layout

```
aqp_index/
├── README.md                       (this file)
├── AGENTS.md                       hard rules; sole-writer boundary
├── index.md                        top-level project index (TOC)
├── architecture/
│   ├── index.md                    SSoT map
│   ├── boundaries.md               pointers to repository-split
│   ├── runtimes.md                 pointers to AgentRuntime / BotRuntime / RLRuntime / AnalysisRuntime / WorkflowRuntime / TerraformRuntime / WorkloadRuntime
│   └── data-flow.md                pointers to data-catalog / data-mcp / iceberg / hudi
├── configs/
│   ├── index.md                    consolidated config catalog
│   └── deployment.md               topology + agents config map
├── code-index/
│   ├── index.md                    methodology + budgets
│   ├── modules.md                  aqp/* module map (curator-generated)
│   ├── symbols.md                  public symbol catalog (curator-generated)
│   └── token-budget.md             budgets per area
├── skills/
│   ├── README.md                   how to add a project skill
│   ├── aqp-index-curator-skill.md  the skill the curator runs each pass
│   └── extension.md                how to extend / maintain skills
└── subagents/
    ├── README.md                   subagent registry
    ├── aqp-index-curator.md        operator-facing description + invocation
    └── extension.md                how to add new subagents
```

See [AGENTS.md](AGENTS.md) for the write-boundary contract.
