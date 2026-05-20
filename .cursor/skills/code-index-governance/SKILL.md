# Code Index Governance

Use this skill when a change touches repository boundaries, code search,
agent-readable indexes, or future repo split guidance.

## Workflow

1. Read `docs/repository-split.md`.
2. Read the nearest `AGENTS.md` for the target folder.
3. Search the owning domain before searching the whole repository.
4. Check for forbidden imports across future repo boundaries.
5. Update `docs/code-index-governance.md` when index rules or search
   workflow changes.

## Boundary Checks

```bash
rg --type py "^from aqp(\.|$)|^import aqp(\.|$)" aqp_control_plane/src
rg "aqp_snippets|extractions|inspiration" aqp aqp_control_plane aqp_platform_core
rg "control.local/api|management/backend|management/frontend" docs README.md
```

Do not paste secrets or token values into docs, examples, or transcripts.

