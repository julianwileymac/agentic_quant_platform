# AGENTS.md

Agent contract for the AQP Theia extension.

## Purpose

This extension embeds AQP operator workflows in Theia. It owns AQP widgets,
commands, Auth0/BFF integration, tenancy headers, runtime config, and the
Theia-side kill-switch command.

## Hard Boundaries

1. Keep AQP-specific code inside `theia-extensions/aqp/`.
2. All backend HTTP calls go through `AqpApiService`.
3. Runtime configuration comes from `GET /aqp/config`; do not bake local
   machine paths or secrets into browser code.
4. Keep kill-switch endpoint lists aligned with AQP's `aqp_client` surface.
5. Reference AQP paths through `docs/aqp-monorepo-paths.md`; do not use
   host-specific absolute paths.

## Validation

```bash
yarn build:extensions
yarn build:applications:dev
```

