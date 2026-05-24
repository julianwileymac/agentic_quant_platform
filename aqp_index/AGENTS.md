# AGENTS.md

Agent contract for `aqp_index/`.

## Sole writer

The only agent permitted to write inside this tree is the
[aqp-index-curator](../.cursor/agents/aqp-index-curator.md) subagent.

All other agents — Cursor, subagents, humans operating through Cursor —
have **read-only** access to this folder. The one documented exception
is appending a single one-liner to the repo-root [README.md](../README.md)
or [AGENTS.md](../AGENTS.md) pointing readers into `aqp_index/`.

## Why a sole writer

1. **No drift.** A single curator with an explicit Plan -> Scan -> Diff ->
   Refresh -> Validate pass keeps every link verifiable.
2. **No content duplication.** Files here are pointers + signatures +
   summaries, never copies of canonical text. Canonical text lives in
   [aqp_docs/](../aqp_docs/), [.cursor/rules/](../.cursor/rules/), and
   the source itself.
3. **Token budgets are explicit.** The curator owns
   [code-index/token-budget.md](code-index/token-budget.md) and is the
   only entity authorized to publish per-area budgets that other agents
   rely on.

## Curator obligations

The curator MUST:

1. Cite a specific file path for every claim it writes here. No
   fabrication. If a claim cannot be verified, write a
   `// TODO: verify <reason>` block and link an open question in
   [.cursor/plans/](../.cursor/plans/).
2. Stamp every file with a `> Last refreshed: YYYY-MM-DD by aqp-index-curator`
   line at the top.
3. Generate code indices as signatures only (class / function names + a
   one-line docstring slice). Never paste full implementations.
4. Respect AQP rules 1-47 (see [../AGENTS.md](../AGENTS.md)). Never edit
   Python source, migrations, or production configs - those changes
   belong to other subagents or to humans.
5. Refresh on a clear trigger: any commit that touches
   [../AGENTS.md](../AGENTS.md), [../.cursor/rules/](../.cursor/rules/),
   [../aqp_docs/](../aqp_docs/), [../configs/](../configs/), or the
   public surface of an `aqp_*` top-level package.

## Read-only contract for everyone else

Other agents reading from here SHOULD:

- Prefer `aqp_index/code-index/*.md` to scanning source files when only
  signatures are needed; this is the explicit token-saving win.
- Link to `aqp_index/architecture/*.md` for canonical orientation.
- Open a `.cursor/plans/` note (rather than editing here directly) when
  they notice stale content.
