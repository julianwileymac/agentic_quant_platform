# AQP Theia MCP

Use this skill when adding or reviewing AQP DataMCP, CodebaseMCP, or
code-index integration in the Theia extension.

## Workflow

1. Read `docs/aqp-monorepo-paths.md`.
2. Read `theia-extensions/aqp/AGENTS.md`.
3. Keep backend calls behind `AqpApiService` or a service that composes it.
4. Update `docs/mcp-integration.md` when adding a new MCP-backed surface.
5. Validate with `yarn build:extensions`.

Do not hardcode local absolute paths or secrets.

