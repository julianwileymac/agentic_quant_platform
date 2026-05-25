# Vale configuration

Vale lints docs prose against the Microsoft Writing Style Guide
plus a small AQP-specific style layer.

## Layout

- `.vale.ini` — root config (lives in `aqp_docs/`).
- `.vale/styles/AQP/` — AQP-specific rules (`Simplicity.yml`, `NoTodos.yml`).
- `.vale/styles/Vocab/AQP/accept.txt` — vocabulary that is allowed
  even though dictionaries flag it as misspelled.

## Run

```powershell
# Local
pnpm --filter aqp_docs vale

# Sync the Microsoft style pack (first time only)
vale sync
```

## CI

`.github/workflows/docs-ci.yml` runs Vale on every PR that touches
`aqp_docs/docs/**/*.{md,mdx}`. Errors fail the build; warnings
post as PR comments.

## Severity ladder

Per the GitLab pattern: introduce new rules as `suggestion`. Once
existing violations are fixed, promote to `warning`. Only graduate
to `error` after a clean run across the whole corpus.
