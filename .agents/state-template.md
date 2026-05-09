# `.agents/state-template.md` — cross-session state schema

> Use this template **only** for work that spans multiple Cursor
> sessions / days / restarts. For in-session tracking, prefer
> Cursor's native plan mode + chat todos — those keep the chat
> short and the agent focused.

If you do need to persist state across sessions, copy this template
to `.agents/state.md` (gitignored) or `.agents/state-<topic>.md`
(checked in for shared work) and fill it out. Keep it short.

---

# Active state

```yaml
phase: blueprint        # one of: analyze | blueprint | construct | validate | reflect
mode: slow              # one of: fast | slow
spawned_at: 2026-05-09
last_touched: 2026-05-09
plan_link: <workspace>/.cursor/plans/<plan_id>.plan.md   # Cursor stores plans in the workspace state, not in this repo
```

## Current task

One sentence describing what's actively being worked on. If you can't
fit it into one sentence, the task is too big — split it.

## Plan checklist

Mirror the todos from the linked plan file here so the next session
can read state without opening Cursor:

- [ ] task 1
- [ ] task 2
- [ ] ...

## Blockers

Anything that requires human input or external action before the
agent can resume:

- (none) | or a numbered list

## Last 5 actions (most recent first)

A terse log of what the agent has actually done, with file paths.
Each entry is one line. Trim older entries — this is not a
permanent log, the git history is.

1. (2026-05-09) Wrote `.cursor/rules/runtimes.mdc`.
2. (2026-05-09) Wrote `.cursor/rules/iceberg.mdc`.
3. ...

## Open questions

If the agent paused with unresolved design questions, list them here
so they can be answered async by the human:

- Q: should the gold-tier `aqp_gold_analysis_*` namespace allow
  cross-flow reads? (default: no — each flow's namespace is its own.)

---

## Conventions

- This file is **state of play**, not a journal. Trim aggressively.
- Don't paste large code excerpts here — link to the file.
- Don't paste full chat history here — the chat is the chat.
- If the work finishes, delete the file (or leave a 2-line
  "completed: <PR-link>" so the next session knows).
- If a plan supersedes this state, update the `plan_link` and
  re-sync the checklist before continuing.

## Why a template, not auto-state

The prompt that motivated this rework asked for an automatic
`state.json` that the agent updates after every action. AQP rejects
that pattern — it bloats commits, races with the chat history, and
loses signal under noise. The agent should update this file
**deliberately**, only when crossing a session boundary, and only
with information the next session genuinely needs.
