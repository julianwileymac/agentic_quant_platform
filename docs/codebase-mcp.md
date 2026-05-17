# Codebase MCP — native agent view of the AQP source tree

> Companion to [docs/data-mcp.md](data-mcp.md). The Codebase MCP is a
> sibling package to `aqp.data.mcp` that exposes the AQP repository
> itself to agents and external IDEs as a tool catalog.

## Why a sibling package

DataMCP owns the agent-readable view of the **data plane**: catalogs,
namespaces, Iceberg slices, ownership graph, sinks, pipelines,
discovery. Codebase MCP owns the agent-readable view of the **source
tree**: file → symbol → call relationships, lexical search, AST
queries, and a tiny LLM-driven elaborator for "what does this
function do?" answers.

Splitting them keeps the registries focused (different scopes:
`data:*` vs `code:*`), and lets the codebase package ship a workspace
allow-list + secret deny-list policy that doesn't belong on data
tools.

## Package layout

```
aqp/codebase/mcp/
├── base.py                 # CodebaseMCPTool ABC (mirrors DataMCPTool)
├── registry.py             # CODEBASE_MCP_TOOLS + @register_codebase_mcp_tool
├── policy.py               # workspace allow-list + secret deny-list
├── server.py               # /mcp/codebase/* HTTP + stdio runner
├── index/
│   ├── ast_index.py        # tree-sitter (with stdlib ast fallback for Python)
│   ├── graph.py            # adjacency graph (file -> symbol -> symbol)
│   ├── ripgrep.py          # rg wrapper + pure-Python fallback
│   └── embeddings.py       # chunker bridging into HierarchicalRAG.index_chunks
└── tools/
    ├── search.py           # codebase.search (hybrid AST + lexical)
    ├── graph.py            # codebase.get_repo_graph
    ├── find.py             # codebase.find_definition / .find_references
    └── elaborate.py        # codebase.elaborate_finding (router_complete)
```

## Hard rules

1. **Rule 2 (LLM calls).** `codebase.elaborate_finding` is the only
   tool that calls an LLM, and it routes through
   [`router_complete`](../aqp/llm/providers/router.py). No
   `litellm.completion` / vendor SDK / raw HTTP to an LLM endpoint
   anywhere under `aqp/codebase/`.
2. **Rule 11 (RAG).** Code embeddings flow through
   `HierarchicalRAG.index_chunks` into the new `code_chunks` corpus
   ([aqp/rag/orders.py](../aqp/rag/orders.py)). The indexer never
   touches Redis or pgvector directly.
3. **Rule 22 (DataMCP boundary).** Agents reach the codebase only
   through `CodebaseMCPTool` subclasses. The bridge in
   [aqp/agents/tools/codebase_mcp_bridge.py](../aqp/agents/tools/codebase_mcp_bridge.py)
   auto-installs them into `TOOL_REGISTRY`.
4. **Policy.** `policy.enforce_path_inside_workspace` and
   `policy.enforce_no_secret_globs` are mandatory. Secrets denied by
   default: `.env`, `*.pem`, `secrets/*`, `*.key`, `id_rsa*`.
5. **No `exec` / `eval` of file contents.** Ever.

## Tool surface

- `codebase.search(query, *, language=None, kind=None, k=20, mode='hybrid')`
- `codebase.get_repo_graph(*, file=None, depth=1)`
- `codebase.find_definition(symbol)`
- `codebase.find_references(symbol)`
- `codebase.elaborate_finding(file, range, *, model_alias=None)`

## Mount points

- **HTTP**: `/mcp/codebase/*` via `build_codebase_mcp_router()`
  mounted in [aqp/api/main.py](../aqp/api/main.py) next to the
  existing `_build_data_mcp_router()` block.
- **stdio**: console script `aqp-codebase-mcp` registered under
  `[project.scripts]` in [pyproject.toml](../pyproject.toml).

## Agent specs that consume it

- [`configs/agents/codebase_assistant.yaml`](../configs/agents/codebase_assistant.yaml)
  — read-only navigator (quick tier).
- [`configs/agents/codebase_refactorer.yaml`](../configs/agents/codebase_refactorer.yaml)
  — deep-tier code reviewer; opt-in SERA via `model.provider = sera`
  once Phase 2.5 is configured (see [sera.md](sera.md)).
