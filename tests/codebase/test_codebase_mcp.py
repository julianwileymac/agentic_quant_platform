"""Tests for the Phase 2 Codebase MCP package.

Covers:

- :class:`CodebaseMCPTool` registry — the five expected tools are
  registered and discoverable.
- :mod:`aqp.codebase.mcp.policy` rejects paths outside the workspace
  root and the configured secret globs.
- :func:`aqp.codebase.mcp.index.index_workspace` parses Python files
  via stdlib ``ast`` and TypeScript via the regex fallback.
- :class:`CodeGraph` builds correct ``contains`` / ``defines`` edges.
- :mod:`aqp.codebase.mcp.index.ripgrep` falls back to a Python scan
  when ``rg`` is not on PATH.
- The bridge installer (``install_codebase_mcp_tools``) registers
  every tool into a target registry.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aqp.codebase.mcp import (
    CODEBASE_MCP_TOOLS,
    CodebaseMCPTool,
    MCPPolicyError,
    MCPToolContext,
    MCPToolResult,
    get_codebase_mcp_tool,
    list_codebase_mcp_tools,
)
from aqp.codebase.mcp.index import (
    build_graph_from_symbols,
    index_file,
    index_workspace,
    ripgrep_search,
)
from aqp.codebase.mcp.policy import (
    enforce_no_secret_globs,
    enforce_path_inside_workspace,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_codebase_mcp_tools_registered():
    expected = {
        "codebase.search",
        "codebase.get_repo_graph",
        "codebase.find_definition",
        "codebase.find_references",
        "codebase.elaborate_finding",
    }
    assert expected <= set(CODEBASE_MCP_TOOLS)


def test_list_codebase_mcp_tools_returns_descriptors():
    descriptors = list_codebase_mcp_tools()
    by_name = {d["name"]: d for d in descriptors}
    assert "codebase.search" in by_name
    schema = by_name["codebase.search"]
    assert "inputSchema" in schema
    assert schema["mutates"] is False
    assert "code:read" in schema["required_scopes"]


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


def test_enforce_path_inside_workspace_blocks_escape(tmp_path: Path):
    ctx = MCPToolContext(workspace_root=str(tmp_path))
    with pytest.raises(MCPPolicyError):
        enforce_path_inside_workspace(ctx, "../etc/passwd")


def test_enforce_path_inside_workspace_resolves_relative(tmp_path: Path):
    ctx = MCPToolContext(workspace_root=str(tmp_path))
    (tmp_path / "x.py").write_text("x = 1\n")
    resolved = enforce_path_inside_workspace(ctx, "x.py")
    assert resolved == (tmp_path / "x.py").resolve()


def test_enforce_no_secret_globs_blocks_env_files():
    ctx = MCPToolContext()
    with pytest.raises(MCPPolicyError):
        enforce_no_secret_globs(ctx, "/repo/.env")
    with pytest.raises(MCPPolicyError):
        enforce_no_secret_globs(ctx, "/repo/secrets/openai.json")
    with pytest.raises(MCPPolicyError):
        enforce_no_secret_globs(ctx, "/repo/keys/id_rsa")


def test_enforce_no_secret_globs_allows_normal_python():
    ctx = MCPToolContext()
    enforce_no_secret_globs(ctx, "/repo/aqp/api/main.py")


# ---------------------------------------------------------------------------
# AST index
# ---------------------------------------------------------------------------


def test_index_python_file(tmp_path: Path):
    src = (
        '''"""Module doc."""\n'''
        "from foo import bar\n"
        "\n"
        "FOO_CONST = 1\n"
        "\n"
        "class Spam:\n"
        '    """spam doc"""\n'
        "    def eggs(self):\n"
        '        """eggs doc"""\n'
        "        return 42\n"
        "\n"
        "def free_fn():\n"
        "    return Spam()\n"
    )
    p = tmp_path / "spam.py"
    p.write_text(src)
    symbols = index_file(p)
    names = {(s.name, s.kind) for s in symbols}
    assert ("spam", "module") in names
    assert ("Spam", "class") in names
    assert ("eggs", "method") in names
    assert ("free_fn", "function") in names
    assert ("FOO_CONST", "constant") in names
    assert ("bar", "import") in names


def test_index_typescript_file(tmp_path: Path):
    p = tmp_path / "Foo.tsx"
    p.write_text(
        "export class Foo {\n"
        "  bar() { return 1; }\n"
        "}\n"
        "export const Bazz = () => 1;\n"
        "export function withQ(): void {}\n"
    )
    symbols = index_file(p)
    names = {s.name for s in symbols}
    assert "Foo" in names
    assert "Bazz" in names
    assert "withQ" in names


def test_index_workspace_skips_excluded(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.ts").write_text("export const x = 1;\n")
    (tmp_path / "real.py").write_text("def hello():\n    return 1\n")
    symbols = index_workspace(tmp_path)
    files = {s.file for s in symbols}
    assert any(f.endswith("real.py") for f in files)
    assert not any("node_modules" in f for f in files)
    assert not any(".git" in f for f in files)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def test_build_graph_from_symbols_contains_defines(tmp_path: Path):
    p = tmp_path / "a.py"
    p.write_text("class A:\n    def m(self):\n        return 1\n\ndef f():\n    return 1\n")
    symbols = index_file(p)
    g = build_graph_from_symbols(symbols)
    contains = [e for e in g.edges if e.kind == "contains"]
    defines = [e for e in g.edges if e.kind == "defines"]
    assert any(e.src == str(p) for e in contains)
    assert any("A" in e.src and "m" in e.dst for e in defines)


# ---------------------------------------------------------------------------
# Ripgrep / lexical fallback
# ---------------------------------------------------------------------------


def test_ripgrep_search_finds_match(tmp_path: Path):
    p = tmp_path / "hits.py"
    p.write_text("alpha = 1\nbeta = 2\ngamma = alpha + beta\n")
    matches = ripgrep_search(root=tmp_path, query="alpha", max_results=10)
    assert len(matches) >= 2
    assert all(m.file == str(p) for m in matches)


# ---------------------------------------------------------------------------
# Bridge — installer merges into a target registry
# ---------------------------------------------------------------------------


def test_codebase_mcp_bridge_installs_into_registry():
    from aqp.agents.tools.codebase_mcp_bridge import install_codebase_mcp_tools

    registry: dict[str, type] = {}
    installed = install_codebase_mcp_tools(registry)
    assert set(installed) >= {
        "codebase.search",
        "codebase.get_repo_graph",
        "codebase.find_definition",
        "codebase.find_references",
        "codebase.elaborate_finding",
    }
    assert all(name in registry for name in installed)


# ---------------------------------------------------------------------------
# Tool invocations: read-only tools work end-to-end against a fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_workspace(tmp_path: Path) -> Path:
    (tmp_path / "aqp").mkdir()
    (tmp_path / "aqp" / "core.py").write_text(
        "class Engine:\n"
        "    def run(self):\n"
        "        return 'ok'\n"
        "\n"
        "def helper():\n"
        "    return Engine()\n"
    )
    (tmp_path / "aqp" / "tasks.py").write_text(
        "from aqp.core import Engine\n"
        "\n"
        "def main():\n"
        "    e = Engine()\n"
        "    return e.run()\n"
    )
    return tmp_path


def test_search_tool_end_to_end(fixture_workspace: Path):
    tool = get_codebase_mcp_tool("codebase.search")
    res = tool.invoke(
        ctx=MCPToolContext(
            workspace_root=str(fixture_workspace),
            granted_scopes=("code:read",),
        ),
        query="Engine",
        mode="ast",
        k=10,
    )
    assert isinstance(res, MCPToolResult)
    assert res.ok is True
    matches = res.data["matches"]
    assert any("Engine" in (m.get("symbol_name") or "") for m in matches)


def test_find_definition_tool_end_to_end(fixture_workspace: Path):
    tool = get_codebase_mcp_tool("codebase.find_definition")
    res = tool.invoke(
        ctx=MCPToolContext(
            workspace_root=str(fixture_workspace),
            granted_scopes=("code:read",),
        ),
        symbol="Engine",
    )
    assert res.ok is True
    defs = res.data["definitions"]
    assert any(d["name"] == "Engine" and d["kind"] == "class" for d in defs)


def test_repo_graph_tool_end_to_end(fixture_workspace: Path):
    tool = get_codebase_mcp_tool("codebase.get_repo_graph")
    res = tool.invoke(
        ctx=MCPToolContext(
            workspace_root=str(fixture_workspace),
            granted_scopes=("code:read",),
        ),
        depth=1,
    )
    assert res.ok is True
    assert res.rows_returned > 0


def test_policy_rejects_missing_scope():
    tool = get_codebase_mcp_tool("codebase.search")
    res = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        query="anything",
    )
    assert res.ok is False
    assert "policy" in (res.error or "").lower()
