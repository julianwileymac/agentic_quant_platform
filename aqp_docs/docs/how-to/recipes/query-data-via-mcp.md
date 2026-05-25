---
title: 'Recipe: query data via MCP'
summary: 'Invoke a data.*  MCP tool from an agent context (no direct Postgres / Iceberg reads).'
owner: data-team
last_reviewed: 2026-05-25
audience: both
---

# Recipe: query data via MCP

AGENTS rule 22: agents NEVER read Postgres or Iceberg directly.
Every catalog / dataset / entity / pipeline read goes through a
registered `DataMCPTool`. The bridge auto-installs every tool into
the agent `TOOL_REGISTRY`; the same tools are reachable externally
over HTTP at `/mcp/data` and via the `aqp-data-mcp` stdio binary.

## From inside an agent

```python
from aqp.agents.tools import TOOL_REGISTRY

tool = TOOL_REGISTRY["data.discovery.browse"]
result = tool.invoke({"namespace_prefix": "aqp_silver_yfinance"})
print(result["entries"])
```

## From outside the platform (HTTP)

```powershell
curl -X POST http://localhost:8000/mcp/data/tools/data.discovery.browse/invoke `
    -H "Content-Type: application/json" `
    -H "Authorization: Bearer <m2m_token>" `
    -d '{"namespace_prefix":"aqp_silver_yfinance"}'
```

## From a Cursor/Continue/Cline agent (stdio)

Register the stdio binary as an MCP server in the editor:

```json
{
  "mcpServers": {
    "aqp-data": {
      "command": "aqp-data-mcp",
      "env": { "AQP_MCP_DATA_CANONICAL_URI": "http://localhost:8000/mcp/data" }
    }
  }
}
```

## Where to add a new tool

Subclass [`DataMCPTool`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/data/mcp/base.py)
under `aqp/data/mcp/tools/`, decorate with `@register_data_mcp_tool`,
and the bridge does the rest. See
[Concept: data MCP](../../concepts/data/data-mcp.md).

## RFC 9728 + 8707 conformance

Every AQP MCP server publishes Protected Resource Metadata at
`/.well-known/oauth-protected-resource[/...]` and validates the
`aud` claim on incoming tokens against the deployment's canonical
URI. The docs site's own MCP server lives at
[https://docs.aqp.fund/mcp](/mcp).

## Deeper reads

- [Concept: data MCP](../../concepts/data/data-mcp.md)
- [Concept: codebase MCP](../../concepts/data/codebase-mcp.md)
- [Concept: pgvector control plane](../../concepts/data/pgvector-control-plane.md)
- [Concept: MCP risk tools](../../concepts/data/mcp-risk-tools.md)
