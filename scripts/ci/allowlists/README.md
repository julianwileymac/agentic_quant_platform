# Phase 0 lint allowlists

Each `<lint_name>.txt` file in this directory is the escape hatch for
the corresponding `scripts/ci/check_<lint_name>.py` lint script. One
repo-relative path per line, blank lines and lines starting with `#`
ignored. Trailing `# comment` is preserved — use it for the removal
deadline (mandatory).

Format:

```
aqp/agents/legacy/foo.py  # TODO(phase-1): remove by 2026-08-15
```

Loader: `scripts/ci/_lint_allowlist.py::load_allowlist`.

Allowlists must NEVER drift unbounded. Every entry needs a removal
deadline. CI rejects PRs that add to an allowlist without one (TODO:
add a meta-lint in Phase 1 that checks the trailing comment shape).
