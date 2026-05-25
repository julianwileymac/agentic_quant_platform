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
- [docs/architecture.md](docs/architecture.md) — process diagram, the
  four extension mechanisms, RPC, MCP wiring
- [docs/extensions.md](docs/extensions.md) — per-extension reference
- [docs/cli-entrypoint.md](docs/cli-entrypoint.md) — `aqp-cli ide` cookbook
- [docs/mcp-integration.md](docs/mcp-integration.md) — DataMCP +
  CodebaseMCP wiring details (AQP rule 49)
- [docs/research-copilot.md](docs/research-copilot.md) — Theia AI
  chat agent
- [docs/notebook.md](docs/notebook.md) — Perspective MIME renderer +
  notebook scaffolder
- [docs/quant-widgets.md](docs/quant-widgets.md) — SpecAuthor /
  RunInspector / BacktestRunner reference
- [docs/deployment.md](docs/deployment.md) — Docker + K8s + Theia Cloud
- [docs/retire-vendored-workspace.md](docs/retire-vendored-workspace.md)
  — checklist to delete the byte-identical `test_theia/theia-ide`
- [docs/aqp-monorepo-paths.md](docs/aqp-monorepo-paths.md) — AQP path
  contract used by the Theia extension
- Per-extension contracts (all six):
  - [theia-extensions/aqp/README.md](theia-extensions/aqp/README.md) +
    [AGENTS.md](theia-extensions/aqp/AGENTS.md)
  - [theia-extensions/aqp-shell/README.md](theia-extensions/aqp-shell/README.md) +
    [AGENTS.md](theia-extensions/aqp-shell/AGENTS.md)
  - [theia-extensions/aqp-mcp-bridge/README.md](theia-extensions/aqp-mcp-bridge/README.md) +
    [AGENTS.md](theia-extensions/aqp-mcp-bridge/AGENTS.md)
  - [theia-extensions/aqp-research-copilot/README.md](theia-extensions/aqp-research-copilot/README.md) +
    [AGENTS.md](theia-extensions/aqp-research-copilot/AGENTS.md)
  - [theia-extensions/aqp-notebook-quant/README.md](theia-extensions/aqp-notebook-quant/README.md) +
    [AGENTS.md](theia-extensions/aqp-notebook-quant/AGENTS.md)
  - [theia-extensions/aqp-quant/README.md](theia-extensions/aqp-quant/README.md) +
    [AGENTS.md](theia-extensions/aqp-quant/AGENTS.md)

## Parent-repo entry points

- [../AGENTS.md](../AGENTS.md) — AQP monorepo agent contract
- [../aqp_docs/docs/intro/index.md](../aqp_docs/docs/intro/index.md) — AQP documentation index
- [../aqp_docs/docs/concepts/platform/aqp-monorepo-paths.md](../aqp_docs/docs/concepts/platform/aqp-monorepo-paths.md) —
  canonical monorepo path map (now includes `aqp_ide/`)

## Scope boundaries

1. This folder is a white-labeled Theia IDE distribution + **six** AQP
   compile-time extensions:
   - `theia-extensions/aqp/` (existing — Auth0 + operator widgets + halt)
   - `theia-extensions/aqp-shell/` (white-label + filters)
   - `theia-extensions/aqp-mcp-bridge/` (Theia AI MCP wiring for AQP)
   - `theia-extensions/aqp-research-copilot/` (Theia AI chat agent)
   - `theia-extensions/aqp-notebook-quant/` (Perspective MIME + scaffolder)
   - `theia-extensions/aqp-quant/` (SpecAuthor / RunInspector / BacktestRunner)
2. Keep AQP-specific behavior isolated to `theia-extensions/aqp*/` and
   to integration wiring (`browser.Dockerfile`,
   `applications/browser/package.json`). Don't sprinkle AQP imports
   into core Theia files.
3. Keep browser/electron target scope explicit in docs and commands.
4. Validate script names against root [package.json](package.json)
   before documenting them.
5. Reference AQP paths through the in-folder
   [docs/aqp-monorepo-paths.md](docs/aqp-monorepo-paths.md). For
   monorepo-wide references, use
   [../aqp_docs/docs/concepts/platform/aqp-monorepo-paths.md](../aqp_docs/docs/concepts/platform/aqp-monorepo-paths.md).
6. Don't import from `agentic_quant_platform` source code into Theia
   extension TypeScript — go through HTTP (`AqpApiService`) or the
   DataMCP / CodebaseMCP HTTP surfaces.
7. The canonical entrypoint is **`aqp-cli ide`**. Direct `yarn` is
   inner-loop dev only; never document a production / Docker / K8s
   workflow that doesn't go through the CLI.
8. Every AQP-flavoured LLM call MUST go through AQP's `router_complete`
   gateway (AQP rule 2). The `aqp-research-copilot-ext` is the only
   sanctioned consumer; it imports `RouterCompleteClient` and forbids
   vendor SDK usage.
9. Every MCP registration carries the per-MCP `aud` claim (AQP rule 49)
   — no token passthrough across audiences. Lives in
   `aqp-mcp-bridge-ext`.

## Build commands

The canonical operator entrypoint is the **`aqp-cli ide`** command
group documented at [docs/cli-entrypoint.md](docs/cli-entrypoint.md):

```bash
aqp-cli ide install        # one-time bootstrap (`yarn install`)
aqp-cli ide build --dev    # yarn build:extensions + build:applications:dev
aqp-cli ide start --open   # spawn Theia + open in browser
aqp-cli ide doctor         # preflight checks (yarn, port, auth, lockfile)
```

The native Theia commands are still valid for inner-loop development:

```bash
# From this folder
yarn install
yarn build:extensions
yarn build:applications:dev
```

These commands are NOT chained from the monorepo's top-level `Makefile`
(which builds the AQP Python/Vite stack). The Theia build is a
standalone step driven by `aqp-cli ide`.

## Docs governance

- Label docs as `active`, `migration`, `rollback`, or `archive` where
  applicable.
- Archive transient notes under [docs/archive/](docs/archive/).
- Cross-repo doc cross-links go through the path contract above; do
  not hardcode absolute paths.
