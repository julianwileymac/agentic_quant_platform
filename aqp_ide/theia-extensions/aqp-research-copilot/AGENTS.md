# AGENTS.md

Agent contract for `theia-ide-aqp-research-copilot-ext`.

## Purpose

The "AQP Research Copilot" is a Theia AI `ChatAgent` purpose-built for AQP's
five hash-locked spec runtimes (Agent / Bot / RL / Analysis / Workflow) and
the 9 backtest engines. It exposes:

1. The bridged DataMCP + CodebaseMCP tools from `theia-ide-aqp-mcp-bridge-ext`.
2. A curated set of in-process **tool functions** that wrap AQP REST surfaces
   (`/agents`, `/workflows`, `/bots`, `/rl`, `/analysis`, `/backtest`) so
   the copilot can drive spec authoring + run inspection workflows without
   the user leaving the chat panel.
3. **Prompt fragments** for spec authoring (Agent / Bot / RL / Analysis /
   Workflow) and factor research, registered with Theia AI's prompt
   registry so users can `/` them into a chat session.

## Hard boundaries

1. **All LLM calls** route through AQP's `router_complete` HTTP surface
   (rule 2). This extension MUST NOT import any vendor SDK (LiteLLM,
   OpenAI, Anthropic, Ollama, vLLM) and MUST NOT use any of the bundled
   `@theia/ai-anthropic` / `@theia/ai-openai` / `@theia/ai-ollama` model
   adapters directly. The chat agent registers a custom `LanguageModel`
   that delegates to `RouterCompleteClient`.
2. **Tool functions** wrap existing AQP REST endpoints through
   `AqpApiService` (from `theia-ide-aqp-ext`). They MUST be idempotent
   from the LLM's perspective — return the same structured result for the
   same input — so multi-step workflows are replayable.
3. **No secrets in chat output.** The router-complete client redacts the
   bearer token before any log/print/UI render
   (`.cursor/rules/aqp-management-engine.mdc`).
4. **Step-up gates.** Tool functions that map to AQP step-up-protected
   endpoints (kill switch, every `/halt` route, every `/me/byok/*` DELETE,
   `/tenancy/invites` create, every Terraform write) MUST surface a
   confirmation prompt in the chat UI before invocation and propagate the
   browser's step-up token (rule 52).
5. **Cross-extension dependency** on `theia-ide-aqp-ext` (for
   `AqpApiService`, `Auth0Service`, `AqpTenancyStore`) AND
   `theia-ide-aqp-mcp-bridge-ext` (for MCP server name constants). Both
   are upstream from this package.

## Validation

```bash
yarn build:extensions
yarn build:applications:dev
```

After build, verify in the running IDE:
- "AQP Research Copilot" appears in the AI Configuration view.
- Chat session can call `aqp.spec.list_agent_specs` and gets a JSON array.
- `/spec-authoring` prompt fragment is selectable from the chat input.
- LLM responses arrive (proving `router_complete` is reachable).
