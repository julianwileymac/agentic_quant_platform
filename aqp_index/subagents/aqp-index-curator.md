# aqp-index-curator

> Last refreshed: 2026-05-23 (seed).

## Definition

The Cursor subagent definition lives at
[../../.cursor/agents/aqp-index-curator.md](../../.cursor/agents/aqp-index-curator.md).
This page is the operator-facing description.

## Scope

The curator is the **sole writer** of `aqp_index/`. It owns:

- The centralized project index ([../index.md](../index.md)).
- The SSoT architecture pointers under
  [../architecture/](../architecture/).
- The configuration set pointers under [../configs/](../configs/).
- The code indices under [../code-index/](../code-index/) (token-saving
  signatures + module map).
- The project skills registry under [../skills/](../skills/).
- This subagent registry under [../subagents/](../subagents/).

The curator runs on the Anthropic Claude Opus 4.7 Thinking-Max model
(slug `claude-opus-4-7-thinking-max`), chosen for context size and
careful diff-style refresh work.

## When to invoke

Invoke the curator after any commit that touches one of:

- [../../AGENTS.md](../../AGENTS.md)
- [../../.cursor/rules/](../../.cursor/rules/)
- [../../aqp_docs/](../../aqp_docs/)
- [../../configs/](../../configs/)
- The public surface of any `aqp_*` package (top-level `__init__.py`,
  public route or tool registrations).

Also invoke after any change to the skills registry or the subagent
registry under `aqp_index/`.

## What the curator never does

- Edit Python source, migrations, or production configs.
- Modify files outside `aqp_index/` other than one documented exception:
  a one-liner pointer in repo-root [../../README.md](../../README.md) or
  [../../AGENTS.md](../../AGENTS.md).
- Copy prose from `aqp_docs/`. Pointers + signatures + summaries only.
- Fabricate a file path. Cite or open a TODO.

## Procedure

See [../skills/aqp-index-curator-skill.md](../skills/aqp-index-curator-skill.md).
The skill is the procedure the curator runs every pass.

## Invocation

Cursor users invoke the curator with:

```
Task -> subagent_type: aqp-index-curator
Prompt: "Refresh aqp_index based on commit <sha> (or operator request)."
```

The subagent's `description` frontmatter marks it for proactive use
after qualifying commits.
