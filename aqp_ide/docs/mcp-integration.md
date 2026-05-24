# AQP MCP Integration

Status: migration.

The AQP Theia extension should treat AQP DataMCP and CodebaseMCP as remote
or HTTP-facing capabilities exposed by `agentic_quant_platform`, not as
direct source imports.

Canonical AQP docs:

- `agentic_quant_platform/docs/data-mcp.md`
- `agentic_quant_platform/docs/codebase-mcp.md`
- `agentic_quant_platform/docs/code-index-governance.md`

When the extension adds MCP-backed widgets or commands, keep the API calls
inside `theia-extensions/aqp/src/browser/aqp/aqp-api-service.ts` or a
service layered on top of it.

