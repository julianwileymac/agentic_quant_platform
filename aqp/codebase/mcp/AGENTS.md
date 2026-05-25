# AGENTS.md

Agent contract for Codebase MCP.

## Purpose

This package exposes an agent-readable view of the AQP source tree through
`codebase.*` tools. It supports repository navigation, symbol search,
dependency slices, and bounded elaboration.

## Hard Boundaries

1. Do not bypass `CodebaseMCPTool` subclasses for agent-facing source-tree
   access.
2. `codebase.elaborate_finding` is the only LLM-backed tool and must route
   through `router_complete`.
3. Enforce workspace allow-lists and secret deny-lists before reading paths.
4. Do not index `.env`, private keys, kubeconfigs, local warehouses, model
   weights, or credential files.
5. Keep this package focused on code navigation. Data-plane tools belong in
   `aqp/data/mcp/`.

## Repository Split Context

Use `aqp_docs/docs/concepts/platform/repository-split.md` and `aqp_docs/docs/concepts/platform/code-index-governance.md` when
adding new index categories. Future domain roots such as `aqp_client/`,
`aqp_snippets/`, and `aqp_bots/` should be first-class index scopes, not
afterthoughts under the monolith.

