# Token budgets

> Last refreshed: 2026-05-23 (seed).

The curator publishes per-area token budgets that other agents use to
decide whether to read source directly or consult the code index first.

## Suggested seeds

These are starting numbers; the curator refines them after the first
real pass against actual file sizes.

| Area | Read-source budget | Index-first heuristic |
| --- | --- | --- |
| `aqp/agents/` | ~6 K tokens / file | Always consult code-index when the question is "where is X handled". |
| `aqp/rl/` | ~8 K tokens / file | Always index-first; this tree has the heaviest files. |
| `aqp/data/` | ~5 K tokens / file | Index-first for catalog questions; direct-read for specific tool impls. |
| `aqp/api/routes/` | ~3 K tokens / file | Direct-read is usually fine. |
| `aqp_client/src/routes/` | ~3 K tokens / file | Direct-read is fine. |
| `aqp_control_plane/src/aqp_cp/providers/` | ~6 K tokens / file | Index-first; providers are large. |

## Guardrails

- The curator MUST justify a budget change with a measurement (rough
  token count of representative files).
- Other agents MUST NOT cite a budget that does not appear here.
- If an agent finds itself reading source repeatedly to answer the same
  question, it SHOULD file a `.cursor/plans/` note suggesting the curator
  add a dedicated `modules.md` / `symbols.md` entry for that area.
