# theia-ide-aqp-research-copilot-ext

AQP Research Copilot — a Theia AI `ChatAgent` purpose-built for AQP's
spec-runtime + multi-engine backtest pattern. Backed by AQP's
`router_complete` LLM gateway (rule 2); exposes AQP REST + bridged MCP
tools.

## What the copilot does

1. **Spec authoring** — given a natural-language description of a desired
   agent / bot / RL experiment / analysis / workflow, drafts a hash-lock
   compatible `*Spec` YAML and offers to call the matching
   `POST /<runtime>/spec` endpoint to snapshot it.
2. **Spec inspection** — walks the immutable `*_spec_versions` rows for a
   given spec name and explains the diff between versions.
3. **Run launching** — wraps `POST /agents/runs/v2`, `POST /workflows/{name}/run`,
   `POST /bots/{ref}/backtest`, `POST /rl/runs`, `POST /analysis/runs`
   with progress-frame-aware streaming display.
4. **Factor research** — coordinates a multi-step plan that pulls catalog
   data via `data.catalog.*`, runs an analysis flow, summarises the
   result, and suggests a follow-up.
5. **Codebase navigation** — surfaces `codebase.search` /
   `codebase.find_definition` / `codebase.get_repo_graph` results inline.

## What this extension does NOT do

- Open any Theia widget (the AI chat UI is the only surface)
- Call vendor LLM SDKs directly — every completion goes through
  AQP's `router_complete` per rule 2
- Manage MCP server registrations — that is the job of
  `theia-ide-aqp-mcp-bridge-ext`

## Files

- [src/browser/aqp-research-copilot-frontend-module.ts](src/browser/aqp-research-copilot-frontend-module.ts)
- [src/browser/copilot/aqp-research-agent.ts](src/browser/copilot/aqp-research-agent.ts)
- [src/browser/copilot/aqp-tool-functions.ts](src/browser/copilot/aqp-tool-functions.ts)
- [src/browser/copilot/router-complete-client.ts](src/browser/copilot/router-complete-client.ts)
- [src/browser/copilot/prompts/spec-authoring.md](src/browser/copilot/prompts/spec-authoring.md)
- [src/browser/copilot/prompts/factor-research.md](src/browser/copilot/prompts/factor-research.md)
- [src/browser/copilot/prompts/codebase-navigation.md](src/browser/copilot/prompts/codebase-navigation.md)
- [src/common/aqp-copilot-protocol.ts](src/common/aqp-copilot-protocol.ts)

## See also

- [../../docs/research-copilot.md](../../docs/research-copilot.md)
- [../../docs/mcp-integration.md](../../docs/mcp-integration.md)
- `aqp_docs/docs/concepts/data/providers.md` (the router_complete contract, AQP rule 2)
- `aqp_docs/docs/concepts/data/sera.md` (the SERA-32B opt-in)
