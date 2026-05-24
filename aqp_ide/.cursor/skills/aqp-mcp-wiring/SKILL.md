---
name: aqp-mcp-wiring
description: Step-by-step skill for wiring a new AQP-side MCP server into the AQP IDE via `theia-extensions/aqp-mcp-bridge`. Covers the runtime config slot, env vars, RFC 8707 audience, tenancy headers, K8s ConfigMap, CLI knob, and docs.
---

# Wire a new AQP MCP server into the AQP IDE

Use this skill when AQP ships a new first-party MCP surface (today:
`aqp-data-mcp` + `aqp-codebase-mcp`; future: e.g. `aqp-research-papers-mcp`)
and you need the AQP IDE to register it with Theia AI's MCP client.

## Pre-flight

- Confirm the new MCP server publishes a **RFC 9728 Protected
  Resource Metadata** document at
  `/.well-known/oauth-protected-resource/...` (AQP rule 49).
- Confirm the new MCP server validates incoming token `aud` claims
  per RFC 8707 (no token passthrough).
- Pick a stable canonical name for the server (e.g.
  `aqp-research-papers-mcp`). This name is the cross-extension wire
  contract.

## Step 1 — Extend `AqpRuntimeConfig`

In [`aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts`](../../../theia-extensions/aqp/src/common/aqp-protocol.ts):

```typescript
export interface AqpRuntimeConfig {
    // ...existing fields...
    mcp?: {
        data?: AqpMcpConfigSlot;
        codebase?: AqpMcpConfigSlot;
        researchPapers?: AqpMcpConfigSlot;  // <-- ADD
    };
}
```

## Step 2 — Read env vars on the backend

In [`aqp_ide/theia-extensions/aqp/src/node/aqp-config-endpoint.ts`](../../../theia-extensions/aqp/src/node/aqp-config-endpoint.ts):

```typescript
const mcpResearchPapersUrl = process.env.AQP_THEIA_MCP_RESEARCH_PAPERS_URL || '';
const mcpResearchPapersAudience = process.env.AQP_THEIA_MCP_RESEARCH_PAPERS_AUDIENCE || '';

// ...
mcp: {
    data: mcpDataUrl && mcpDataAudience ? { url: mcpDataUrl, audience: mcpDataAudience } : undefined,
    codebase: mcpCodebaseUrl && mcpCodebaseAudience ? { url: mcpCodebaseUrl, audience: mcpCodebaseAudience } : undefined,
    researchPapers: mcpResearchPapersUrl && mcpResearchPapersAudience
        ? { url: mcpResearchPapersUrl, audience: mcpResearchPapersAudience }
        : undefined,
},
```

## Step 3 — Add the canonical name

In [`aqp_ide/theia-extensions/aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts`](../../../theia-extensions/aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts):

```typescript
export const AQP_MCP_SERVER_NAMES = Object.freeze({
    DATA: 'aqp-data-mcp',
    CODEBASE: 'aqp-codebase-mcp',
    RESEARCH_PAPERS: 'aqp-research-papers-mcp',  // <-- ADD
});
```

## Step 4 — Add the surface

In [`aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts`](../../../theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts):

```typescript
export const AQP_MCP_SURFACES: readonly AqpMcpSurface[] = Object.freeze([
    // ...existing entries...
    {
        name: AQP_MCP_SERVER_NAMES.RESEARCH_PAPERS,
        description: 'AQP Research Papers MCP — search, retrieve, summarise.',
        cfgKey: 'researchPapers',
    },
]);
```

`AqpMcpRegistrar.reregisterAll()` automatically iterates over
`AQP_MCP_SURFACES` — no further bridge changes needed.

## Step 5 — Document the env vars

### Docker

In [`aqp_ide/browser.Dockerfile`](../../../browser.Dockerfile)'s `ENV`
block:

```dockerfile
ENV ... \
    AQP_THEIA_MCP_RESEARCH_PAPERS_URL="" \
    AQP_THEIA_MCP_RESEARCH_PAPERS_AUDIENCE=""
```

### K8s

In [`aqp_platform/deployments/kubernetes/aqp-ide/configmap-aqp.yaml`](../../../../aqp_platform/deployments/kubernetes/aqp-ide/configmap-aqp.yaml):

```yaml
AQP_THEIA_MCP_RESEARCH_PAPERS_URL: "https://api.aqp.fund/mcp/research-papers"
AQP_THEIA_MCP_RESEARCH_PAPERS_AUDIENCE: "https://api.aqp.fund/mcp/research-papers"
```

### CLI

In [`aqp_cli/src/aqp_cli/commands/ide.py`](../../../../aqp_cli/src/aqp_cli/commands/ide.py)'s
`_THEIA_ENV_KEYS` tuple:

```python
_THEIA_ENV_KEYS = (
    # ...existing keys...
    "AQP_THEIA_MCP_RESEARCH_PAPERS_URL",
    "AQP_THEIA_MCP_RESEARCH_PAPERS_AUDIENCE",
)
```

## Step 6 — Update docs

1. [`aqp_ide/docs/mcp-integration.md`](../../../docs/mcp-integration.md) —
   add the new server to the "Environment variables" table.
2. [`aqp_ide/docs/research-copilot.md`](../../../docs/research-copilot.md) —
   the copilot picks up the new MCP tools automatically; mention any
   new copilot tool functions that should be added.
3. [`aqp_ide/theia-extensions/aqp-mcp-bridge/README.md`](../../../theia-extensions/aqp-mcp-bridge/README.md) —
   add a row to the "What gets registered" table.

## Step 7 — Validate

```bash
# Build:
yarn build:extensions
yarn build:applications:dev

# Smoke:
aqp-cli ide doctor
aqp-cli ide start --open
# In Theia: Command palette → "AQP: MCP — Show Status"
# The new server should appear with state OK + the correct URL.

# Verify per-MCP audience enforcement on the AQP side:
# The new MCP server should REJECT a token whose `aud` does not match
# AQP_THEIA_MCP_RESEARCH_PAPERS_AUDIENCE.
```

## Step 8 — Reflect into aqp_index

Per the always-on `aqp-index-reflect.mdc` rule, refresh `aqp_index/`
via the `aqp-index-curator` subagent OR open a debt note.

## Don't list

- Don't reuse the AQP API audience for an MCP server (rule 49).
- Don't print bearer tokens in any log.
- Don't bypass the `AqpMcpRegistrar` — adding `MCPServerManager.addOrUpdateServer`
  calls in other extensions creates duplicate registrations and breaks
  the tenancy-driven re-registration loop.
- Don't skip the K8s ConfigMap update — production deployments depend
  on it.
- Don't forget to add the slot to `AqpRuntimeConfig` — the bridge
  silently skips servers whose slot is missing, so a typo here is hard
  to debug.
