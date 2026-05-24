---
name: aqp-index-curator-skill
description: Plan -> Scan -> Diff -> Refresh -> Validate procedure the curator subagent runs on every aqp_index refresh.
owner: aqp-index-curator
last_verified: 2026-05-23
---

# Curator pass procedure

## When to use

Every time the [aqp-index-curator](../../.cursor/agents/aqp-index-curator.md)
subagent is invoked. Mandatory for any change that touches
[../../AGENTS.md](../../AGENTS.md), [../../.cursor/rules/](../../.cursor/rules/),
[../../aqp_docs/](../../aqp_docs/), [../../configs/](../../configs/), or the
public surface of an `aqp_*` package.

## Procedure

### 1. Plan

- State the trigger (`commit <sha> touched <files>` or `operator asked
  for refresh`).
- List the files in `aqp_index/` that the trigger might invalidate.
- If unsure whether a file is invalidated, mark it for verification in
  step 4.

### 2. Scan

Walk these inputs in this order:

1. [../../AGENTS.md](../../AGENTS.md) -> "Repository split routing" + "Hard rules" + "Quick reference".
2. [../../.cursor/rules/](../../.cursor/rules/) -> any new or renamed `.mdc` file.
3. [../../aqp_docs/](../../aqp_docs/) -> all canonical prose.
4. [../../configs/](../../configs/) -> any new YAML or schema change.
5. Public surface of each `aqp_*` package (top-level `__init__.py`,
   public exports, route registrations).

### 3. Diff

For each file in `aqp_index/`:

- Compute what the file claims.
- Verify each claim against its cited source.
- Mark drift: stale link, renamed symbol, missing pointer, or new
  concept that should be added.

### 4. Refresh

- Update only files that drifted.
- Stamp every updated file with `> Last refreshed: YYYY-MM-DD by aqp-index-curator`.
- For any unverifiable claim, write a `// TODO: verify <reason>` block
  and open a [.cursor/plans/](../../.cursor/plans/) note linking back to
  the file.

### 5. Validate

- Spot-check 5 random links per refreshed file - they must resolve.
- Confirm no file under `aqp_index/` carries content (paragraphs of
  prose copied from `aqp_docs/`). Pointers + signatures + summaries
  only.
- Confirm `code-index/modules.md` and `code-index/symbols.md` contain
  signatures only - no pasted bodies.

## Validation checklist

- [ ] Every refreshed file has a fresh `> Last refreshed` line.
- [ ] No new file contains > 50 lines of prose copied from `aqp_docs/`.
- [ ] Every `TODO: verify` block has a linked `.cursor/plans/` note.
- [ ] `git diff aqp_index/` shows only additive / corrective edits;
      nothing outside `aqp_index/` was touched.

## Anti-patterns

- Pasting full function bodies into `code-index/*.md`.
- Editing canonical prose in `aqp_docs/` from this skill - that's a
  separate task and a different subagent.
- Fabricating a path that doesn't exist. If you can't find it, file a
  TODO, never invent.
