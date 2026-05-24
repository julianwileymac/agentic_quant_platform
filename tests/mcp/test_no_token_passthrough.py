"""MCP no-token-passthrough lint (Workstream E).

The 2025-11-25 MCP authorization spec is explicit::

    "MCP servers MUST NOT accept any tokens that were not explicitly
     issued for the MCP server."

The corollary, from the matching Security Best Practices document::

    "The MCP server MUST NOT pass through the token it received from
     the MCP client."

This test enforces the corollary at the source-code level. It walks
every Python file under ``aqp/data/mcp/`` and ``aqp/codebase/mcp/``
and asserts that no module forwards an incoming ``Authorization``
header to an outbound HTTP call.

The check is deliberately conservative: any line that BOTH

- references the variable name ``Authorization`` (in a request header
  context), AND
- passes that value into an outbound ``httpx`` / ``requests`` /
  ``aiohttp`` call

is a violation. The same heuristic catches the more common form ``f"Bearer {request.headers['authorization']}"``.

If a future MCP tool legitimately needs to relay a token (the spec
explicitly forbids this — there is no legitimate case), document the
exception with an inline ``# noqa: aqp-mcp-token-passthrough`` marker.
The linter respects the marker so reviewers see it in diffs.
"""
from __future__ import annotations

import os
import re
from pathlib import Path


MCP_PACKAGES = (
    "aqp/data/mcp",
    "aqp/codebase/mcp",
)


_FORBIDDEN_PATTERNS = (
    # Forwarding the raw Authorization header through ``headers=`` kwargs.
    re.compile(
        r"""headers\s*=\s*\{[^}]*['"]Authorization['"]\s*:\s*request\.headers""",
        re.DOTALL,
    ),
    # f-string injection of the user's Bearer token into upstream calls.
    re.compile(r'f"Bearer \{[^}]*authorization[^}]*\}"', re.IGNORECASE),
    re.compile(r"f'Bearer \{[^}]*authorization[^}]*\}'", re.IGNORECASE),
    # Direct ``request.headers["Authorization"]`` getitem in tool code.
    re.compile(
        r"""request\.headers\s*\[\s*['"]Authorization['"]\s*\]""",
        re.IGNORECASE,
    ),
)

_BYPASS_MARKER = "noqa: aqp-mcp-token-passthrough"


def _repo_root() -> Path:
    """Locate the agentic_quant_platform repo root from this file's path."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "aqp").is_dir():
            return parent
    raise AssertionError("could not locate repo root")


def _iter_mcp_files() -> list[Path]:
    root = _repo_root()
    files: list[Path] = []
    for package in MCP_PACKAGES:
        pkg = root / package
        if not pkg.is_dir():
            continue
        for path in pkg.rglob("*.py"):
            files.append(path)
    return files


def test_no_token_passthrough_in_mcp_packages() -> None:
    """Lint: MCP packages must not forward the user's Bearer token."""
    violations: list[str] = []
    for path in _iter_mcp_files():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for pattern in _FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                # Find the line containing the match; allow the bypass
                # marker for the rare legitimate case (none expected).
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                if line_end == -1:
                    line_end = len(text)
                line = text[line_start:line_end]
                if _BYPASS_MARKER in line:
                    continue
                # Skip the test file itself (regex patterns referenced
                # in this very file would otherwise trip the linter).
                rel = path.relative_to(_repo_root())
                if str(rel).replace("\\", "/").startswith("tests/"):
                    continue
                lineno = text[: match.start()].count("\n") + 1
                violations.append(f"{rel}:{lineno}: {line.strip()[:120]}")
    assert not violations, (
        "MCP packages must not forward incoming Authorization headers "
        "to upstream APIs. Mint a fresh M2M token via M2MTokenIssuer. "
        "Violations:\n"
        + "\n".join(violations)
    )


def test_lint_scans_some_files() -> None:
    """Sanity: the linter is actually finding source files to scan."""
    files = _iter_mcp_files()
    assert files, "no MCP source files found — linter would silently pass"
    # Both packages should contribute.
    paths = [str(p).replace("\\", "/") for p in files]
    assert any("aqp/data/mcp" in p for p in paths)
    assert any("aqp/codebase/mcp" in p for p in paths)
