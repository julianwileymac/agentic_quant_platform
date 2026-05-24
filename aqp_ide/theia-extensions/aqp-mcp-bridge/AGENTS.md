# AGENTS.md

Agent contract for `theia-ide-aqp-mcp-bridge-ext`.

## Purpose

Bridge Theia AI's MCP client (`@theia/ai-mcp`) to AQP's two first-party MCP
surfaces:

- `aqp-data-mcp` — DataMCP tools (`data.*.*`) per AQP hard rule 22.
- `aqp-codebase-mcp` — Codebase MCP tools (`codebase.*.*`) per AQP rule 22.

Both surfaces are served over streamable HTTP and are RFC 9728 / RFC 8707
conformant per AQP rule 49. This extension is the only code in `aqp_ide`
allowed to call `MCPServerManager.addOrUpdateServer(...)` programmatically.

## Hard boundaries

1. Tokens. Every MCP server registration MUST carry an
   `Authorization: Bearer <token>` header minted via
   `Auth0Service.getAccessToken()`. NEVER hardcode a token. NEVER print the
   token. The redacted 4-character prefix rule (`aqp-management-engine.mdc`)
   applies to every log line.
2. Audiences. The `aud` claim in the access token MUST match the canonical
   URI advertised by each MCP server. AQP exposes those as
   `AQP_THEIA_MCP_DATA_AUDIENCE` and `AQP_THEIA_MCP_CODEBASE_AUDIENCE`
   env vars surfaced through `AqpRuntimeConfig.mcp`. NEVER reuse the AQP
   API audience for an MCP server registration — rule 49 forbids token
   passthrough.
3. Tenancy. The `X-AQP-*` headers from `AqpTenancyStore` MUST be forwarded
   on every MCP request so the backend tenancy filter (rule 51) sees the
   active workspace / project / lab.
4. Cross-extension dependency. May depend on `theia-ide-aqp-ext` (for
   `AqpConfigService`, `Auth0Service`, `AqpTenancyStore`). Must NOT
   depend on `theia-ide-aqp-research-copilot-ext` (the dependency goes
   the other way — the copilot uses the bridged MCP servers).
5. No HTTP from this extension. All HTTP to the MCP servers flows
   through `@theia/ai-mcp`'s own transport layer.

## Validation

```bash
yarn build:extensions
yarn build:applications:dev
```

After build, verify in the running IDE:
- `AQP: MCP — Reconnect All` command exists in the command palette.
- The `@theia/ai-mcp-ui` panel lists `aqp-data-mcp` and `aqp-codebase-mcp`
  in a connected state once signed in.
