# AGENTS.md

Agent entry point for the AQP-vendored Theia IDE.

> **New location**: this folder is a vendored copy of the upstream Theia
> IDE workspace, now living inside the `agentic_quant_platform` monorepo
> as `aqp_ide/`. Upstream history is preserved in the original
> `test_theia/theia-ide` checkout; this copy is the canonical source for
> AQP-bound development going forward.

## Canonical docs (in-folder)

- [README.md](README.md)
- [docs/index.md](docs/index.md) — Theia-side index
- [docs/aqp-monorepo-paths.md](docs/aqp-monorepo-paths.md) — AQP path
  contract used by the Theia extension
- [theia-extensions/aqp/README.md](theia-extensions/aqp/README.md)
- [theia-extensions/aqp/AGENTS.md](theia-extensions/aqp/AGENTS.md)

## Parent-repo entry points

- [../AGENTS.md](../AGENTS.md) — AQP monorepo agent contract
- [../aqp_docs/index.md](../aqp_docs/index.md) — AQP documentation index
- [../aqp_docs/aqp-monorepo-paths.md](../aqp_docs/aqp-monorepo-paths.md) —
  canonical monorepo path map (now includes `aqp_ide/`)

## Scope boundaries

1. This folder remains an additive Theia IDE workspace with an AQP
   extension under `theia-extensions/aqp/`. Treat upstream behavior
   changes as carefully as you would in the original Theia repo.
2. Keep AQP-specific behavior isolated to `theia-extensions/aqp/` and
   to integration wiring (`browser.Dockerfile`,
   `applications/browser/package.json`). Don't sprinkle AQP imports
   into core Theia files.
3. Keep browser/electron target scope explicit in docs and commands.
4. Validate script names against root [package.json](package.json)
   before documenting them.
5. Reference AQP paths through the in-folder
   [docs/aqp-monorepo-paths.md](docs/aqp-monorepo-paths.md). For
   monorepo-wide references, use
   [../aqp_docs/aqp-monorepo-paths.md](../aqp_docs/aqp-monorepo-paths.md).
6. Don't import from `agentic_quant_platform` source code into Theia
   extension TypeScript — go through HTTP (`AqpApiService`) or the
   DataMCP / CodebaseMCP HTTP surfaces.

## Build commands (Theia-native)

```bash
# From this folder
yarn install
yarn build:extensions
yarn build:applications:dev
```

These are the same commands documented in the upstream Theia
workspace; they are NOT chained from the monorepo's top-level
`Makefile` (which builds the AQP Python/Vite stack).

## Docs governance

- Label docs as `active`, `migration`, `rollback`, or `archive` where
  applicable.
- Archive transient notes under [docs/archive/](docs/archive/).
- Cross-repo doc cross-links go through the path contract above; do
  not hardcode absolute paths.
