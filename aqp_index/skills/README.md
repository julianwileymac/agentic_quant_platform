# Project skills

> Last refreshed: 2026-05-23 (seed).

## What lives here

One file per **project skill** the curator has registered. A project
skill is an actionable workflow a Cursor Agent should follow when a
matching task lands. Skills are distinct from:

- `.cursor/rules/*.mdc` (always-on or glob-scoped rule files).
- `.cursor/agents/*.md` (subagent definitions).
- `aqp_snippets/` (curated external code).

## Anatomy of a skill file

```markdown
---
name: <slug>
description: <one sentence describing when to use it>
owner: <who curates it>
last_verified: YYYY-MM-DD
---

# <Human title>

## When to use

- bullet
- bullet

## Procedure

1. step
2. step
3. step

## Validation

- how the agent confirms success
```

Cursor's first-party skill format
([SKILL.md](https://cursor.com/docs/agent/skills)) is compatible with
this layout - the YAML frontmatter is the same `name` + `description`.

## How to add a skill

Read [extension.md](extension.md). The high-level steps:

1. Draft the skill file under [skills/](.) following the template.
2. Add a Cursor-native pointer at
   `.cursor/skills/<slug>/SKILL.md` if you want it to auto-load.
3. Open a `.cursor/plans/` note asking the
   [aqp-index-curator](../../.cursor/agents/aqp-index-curator.md) to
   verify + register the skill in the registry below.

## Registry

The registry is rebuilt on each curator pass.

| Skill | When | Owner | Last verified |
| --- | --- | --- | --- |
| [aqp-index-curator-skill](aqp-index-curator-skill.md) | Every aqp_index refresh | aqp-index-curator | 2026-05-23 |
