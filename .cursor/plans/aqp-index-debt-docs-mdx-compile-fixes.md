# aqp_index debt note — docs MDX compile fixes

## Changed surface
- `aqp_docs/` docs content and site wiring for MDX/Docusaurus compile compatibility:
  - fixed MDX-invalid angle-bracket tokens in multiple docs pages
  - corrected docs homepage component imports
  - added missing docs runtime dependency `@scalar/api-reference-react`
  - updated Docusaurus config/plugin compatibility for local dev startup
  - updated sidebar decision IDs to current document slugs

## aqp_index files to refresh
- `aqp_index/project_index/*` entries that summarize docs tooling and dependency surfaces
- `aqp_index/architecture/*` pointers for docs-site runtime/dependency expectations
- `aqp_index/code_indices/*` signatures or references that mention docs route/sidebar IDs
- `aqp_index/skills_registry/*` only if docs-related operational guidance references outdated paths

## One-line curator summary
Refresh aqp_index docs references to reflect MDX-safe docs content, corrected sidebar IDs, and the new Scalar API reference dependency used by `aqp_docs`.
