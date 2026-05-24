# theia-ide-aqp-mcp-bridge-ext

Pre-configures Theia AI MCP servers for AQP's `aqp-data-mcp` and
`aqp-codebase-mcp` surfaces with the correct Auth0 bearer + RFC 8707
audience + tenancy headers.

## Why this exists

The bundled `@theia/ai-mcp` extension provides a generic MCP client but
expects a human to type the server URL, headers, and audience into the
preferences UI. AQP knows the right values at runtime — they are served by
`GET /aqp/config` from the Theia backend. This bridge reads that config and
calls `MCPServerManager.addOrUpdateServer(...)` for each AQP MCP surface.

## What gets registered

| Name | URL env var | Audience env var | Tools exposed |
| --- | --- | --- | --- |
| `aqp-data-mcp` | `AQP_THEIA_MCP_DATA_URL` | `AQP_THEIA_MCP_DATA_AUDIENCE` | `data.*` (catalog, datasets, lineage, kubernetes, terraform, agents, ownership, oauth, vector, …) |
| `aqp-codebase-mcp` | `AQP_THEIA_MCP_CODEBASE_URL` | `AQP_THEIA_MCP_CODEBASE_AUDIENCE` | `codebase.search`, `codebase.find_definition`, `codebase.find_references`, `codebase.get_repo_graph`, `codebase.elaborate_finding` |

Both registrations carry:

- `Authorization: Bearer <auth0-access-token>` minted via the per-MCP
  audience (rule 49 — no token passthrough across audiences).
- `X-AQP-Workspace` / `X-AQP-Project` / `X-AQP-Lab` / `X-AQP-Org` /
  `X-AQP-Team` from `AqpTenancyStore` (rule 51 — tenancy isolation).
- `User-Agent: AQP-IDE/<version> (theia-ide-aqp-mcp-bridge-ext)` for
  audit attribution.

## Commands

| Command | Action |
| --- | --- |
| `AQP: MCP — Reconnect All` | Re-fetch `/aqp/config`, re-mint tokens, re-register both MCP servers |
| `AQP: MCP — Show Status` | Open a MessageService notification with the registration state of both servers |

## Files

- [src/browser/aqp-mcp-bridge-frontend-module.ts](src/browser/aqp-mcp-bridge-frontend-module.ts)
- [src/browser/mcp/aqp-mcp-registrar.ts](src/browser/mcp/aqp-mcp-registrar.ts)
- [src/browser/mcp/aqp-mcp-server-spec.ts](src/browser/mcp/aqp-mcp-server-spec.ts)
- [src/browser/commands/aqp-mcp-contribution.ts](src/browser/commands/aqp-mcp-contribution.ts)
- [src/common/aqp-mcp-protocol.ts](src/common/aqp-mcp-protocol.ts)

## See also

- [../../docs/mcp-integration.md](../../docs/mcp-integration.md)
- [../../docs/research-copilot.md](../../docs/research-copilot.md)
- `aqp_docs/data-mcp.md` (DataMCP boundary, AQP rule 22)
- `aqp_docs/codebase-mcp.md` (Codebase MCP, AQP rule 22)
