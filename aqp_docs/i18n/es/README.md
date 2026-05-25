# Spanish locale (`es`)

First non-English locale for the AQP docs site. Phase 5 of the
migration plan.

## What lives here

- `code.json` — translated UI strings used by Docusaurus theme
  components. Source pulled from `i18n/en/code.json` by
  `pnpm --filter aqp_docs write-translations`.
- `docusaurus-plugin-content-docs/current/<route>.md(x)` — Crowdin
  fills these in after the initial English source is uploaded.

## Workflow

```powershell
# Push English sources to Crowdin (CI runs this on every merge to main).
pnpm --filter aqp_docs crowdin:upload

# Download translated bundles (CI opens a daily PR).
pnpm --filter aqp_docs crowdin:download
```

## Excluded from translation

The auto-generated trees stay English-only:

- `docs/reference/python/**`
- `docs/reference/api/**`
- `docs/reference/manage-api/**`
- `docs/reference/data-dictionary/**`

Translating Pydantic field names and OpenAPI operation ids is
anti-value.

## MDX warning

Crowdin's MDX support is not 1:1 — complex JSX components MUST be
extracted into non-translated React modules under `aqp_docs/src/`
and imported into the MDX file. The plan's "Caveats" section
documents the pattern.
