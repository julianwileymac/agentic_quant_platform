"""AST indexing for the codebase MCP.

Tree-sitter is the preferred backend (Python / TypeScript / TSX /
SQL / Markdown). When it is unavailable we fall back to:

- Python's stdlib :mod:`ast` for ``.py`` files.
- A best-effort regex-based scanner for everything else (returns
  file-level symbols only).

The fallback path is what powers the unit tests on environments that
do not ship a tree-sitter binding; production deployments install
``tree-sitter-language-pack`` via the new ``[codebase]`` extra.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Literal

logger = logging.getLogger(__name__)


SymbolKind = Literal[
    "module",
    "class",
    "function",
    "method",
    "constant",
    "import",
    "section",
]


@dataclass(slots=True)
class Symbol:
    """A code symbol discovered by the index.

    All paths are absolute filesystem paths; ranges are 1-based line
    ranges inclusive on both ends so the WebSocket consumers can use
    them directly in editor URLs.
    """

    name: str
    kind: SymbolKind
    file: str
    start_line: int
    end_line: int
    parent: str | None = None
    language: str = ""
    docstring: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


_PY_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def index_file(path: str | Path) -> list[Symbol]:
    """Return a list of :class:`Symbol` for ``path``.

    Empty when the language is unsupported or the file is unreadable.
    """
    p = Path(path)
    if not p.is_file():
        return []
    suffix = p.suffix.lower()
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        logger.debug("index_file read failed for %s: %s", p, exc)
        return []

    if suffix == ".py":
        return _index_python(p, text)
    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        return _index_typescript(p, text)
    if suffix in {".sql"}:
        return _index_sql(p, text)
    if suffix in {".md", ".mdx"}:
        return _index_markdown(p, text)
    if suffix in {".yaml", ".yml"}:
        return [
            Symbol(
                name=p.stem,
                kind="module",
                file=str(p),
                start_line=1,
                end_line=max(1, text.count("\n") + 1),
                language="yaml",
            )
        ]
    return []


def index_workspace(
    root: str | Path,
    *,
    include_globs: Iterable[str] | None = None,
    exclude_globs: Iterable[str] | None = None,
) -> list[Symbol]:
    """Walk ``root`` and index every supported file.

    ``include_globs`` defaults to a tight Python/TS/TSX/SQL/MD/YAML
    set. ``exclude_globs`` defaults to ``.git``, ``node_modules``,
    ``__pycache__``, ``var``, ``dist``, ``build``.
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        return []
    include = tuple(include_globs or (
        "*.py", "*.ts", "*.tsx", "*.js", "*.jsx",
        "*.sql", "*.md", "*.mdx", "*.yaml", "*.yml",
    ))
    exclude = tuple(exclude_globs or (
        ".git", "node_modules", "__pycache__", "var",
        "dist", "build", ".venv", "venv", ".mypy_cache",
        ".pytest_cache",
    ))

    symbols: list[Symbol] = []
    for candidate in _walk_files(root_path, include, exclude):
        symbols.extend(index_file(candidate))
    return symbols


def _walk_files(
    root: Path, include: tuple[str, ...], exclude: tuple[str, ...]
) -> Iterator[Path]:
    for child in root.iterdir():
        try:
            if any(child.match(pat) or child.name == pat for pat in exclude):
                continue
            if child.is_symlink():
                continue
            if child.is_dir():
                yield from _walk_files(child, include, exclude)
            elif child.is_file():
                for pat in include:
                    if child.match(pat):
                        yield child
                        break
        except Exception:  # noqa: BLE001
            logger.debug("walk skip %s", child, exc_info=True)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def _index_python(path: Path, text: str) -> list[Symbol]:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        logger.debug("python parse failed for %s: %s", path, exc)
        return [
            Symbol(
                name=path.stem,
                kind="module",
                file=str(path),
                start_line=1,
                end_line=max(1, text.count("\n") + 1),
                language="python",
                metadata={"parse_error": str(exc)},
            )
        ]

    symbols: list[Symbol] = [
        Symbol(
            name=path.stem,
            kind="module",
            file=str(path),
            start_line=1,
            end_line=max(1, text.count("\n") + 1),
            language="python",
            docstring=ast.get_docstring(tree) or "",
        )
    ]

    def _walk(node: ast.AST, parent_name: str | None = None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                symbols.append(
                    Symbol(
                        name=child.name,
                        kind="class",
                        file=str(path),
                        start_line=child.lineno,
                        end_line=getattr(child, "end_lineno", child.lineno) or child.lineno,
                        parent=parent_name,
                        language="python",
                        docstring=ast.get_docstring(child) or "",
                    )
                )
                _walk(child, parent_name=child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind: SymbolKind = "method" if parent_name else "function"
                symbols.append(
                    Symbol(
                        name=child.name,
                        kind=kind,
                        file=str(path),
                        start_line=child.lineno,
                        end_line=getattr(child, "end_lineno", child.lineno) or child.lineno,
                        parent=parent_name,
                        language="python",
                        docstring=ast.get_docstring(child) or "",
                    )
                )
                _walk(child, parent_name=parent_name)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                module = ""
                if isinstance(child, ast.ImportFrom):
                    module = child.module or ""
                for alias in child.names:
                    symbols.append(
                        Symbol(
                            name=alias.asname or alias.name,
                            kind="import",
                            file=str(path),
                            start_line=child.lineno,
                            end_line=child.lineno,
                            parent=parent_name,
                            language="python",
                            metadata={"module": module, "imported": alias.name},
                        )
                    )
            elif isinstance(child, ast.Assign):
                # Module-level UPPER_SNAKE constants only — keep the
                # symbol table tight.
                if parent_name is None:
                    for target in child.targets:
                        if (
                            isinstance(target, ast.Name)
                            and _PY_NAME_RE.match(target.id)
                            and target.id.isupper()
                        ):
                            symbols.append(
                                Symbol(
                                    name=target.id,
                                    kind="constant",
                                    file=str(path),
                                    start_line=child.lineno,
                                    end_line=getattr(child, "end_lineno", child.lineno)
                                    or child.lineno,
                                    parent=None,
                                    language="python",
                                )
                            )
            else:
                _walk(child, parent_name=parent_name)

    _walk(tree)
    return symbols


# ---------------------------------------------------------------------------
# TypeScript / JavaScript
# ---------------------------------------------------------------------------


_TS_CLASS_RE = re.compile(r"^\s*export\s+(?:default\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)")
_TS_FUNC_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_TS_ARROW_RE = re.compile(
    r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:=]"
)
_TS_INTERFACE_RE = re.compile(
    r"^\s*export\s+(?:type|interface)\s+([A-Za-z_][A-Za-z0-9_]*)"
)


def _index_typescript(path: Path, text: str) -> list[Symbol]:
    symbols: list[Symbol] = [
        Symbol(
            name=path.stem,
            kind="module",
            file=str(path),
            start_line=1,
            end_line=max(1, text.count("\n") + 1),
            language="typescript",
        )
    ]
    for i, line in enumerate(text.splitlines(), start=1):
        if m := _TS_CLASS_RE.match(line):
            symbols.append(
                Symbol(
                    name=m.group(1),
                    kind="class",
                    file=str(path),
                    start_line=i,
                    end_line=i,
                    language="typescript",
                )
            )
        elif m := _TS_FUNC_RE.match(line):
            symbols.append(
                Symbol(
                    name=m.group(1),
                    kind="function",
                    file=str(path),
                    start_line=i,
                    end_line=i,
                    language="typescript",
                )
            )
        elif m := _TS_ARROW_RE.match(line):
            symbols.append(
                Symbol(
                    name=m.group(1),
                    kind="constant",
                    file=str(path),
                    start_line=i,
                    end_line=i,
                    language="typescript",
                )
            )
        elif m := _TS_INTERFACE_RE.match(line):
            symbols.append(
                Symbol(
                    name=m.group(1),
                    kind="class",
                    file=str(path),
                    start_line=i,
                    end_line=i,
                    language="typescript",
                    metadata={"ts_kind": "type-or-interface"},
                )
            )
    return symbols


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------


_SQL_CREATE_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(TABLE|VIEW|FUNCTION|INDEX|TYPE|MATERIALIZED\s+VIEW)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_\.\"]*)",
    re.IGNORECASE,
)


def _index_sql(path: Path, text: str) -> list[Symbol]:
    symbols: list[Symbol] = [
        Symbol(
            name=path.stem,
            kind="module",
            file=str(path),
            start_line=1,
            end_line=max(1, text.count("\n") + 1),
            language="sql",
        )
    ]
    for i, line in enumerate(text.splitlines(), start=1):
        m = _SQL_CREATE_RE.search(line)
        if not m:
            continue
        kind = m.group(1).lower()
        name = m.group(2).strip('"')
        symbols.append(
            Symbol(
                name=name,
                kind="class" if "table" in kind or "view" in kind or "type" in kind else "function",
                file=str(path),
                start_line=i,
                end_line=i,
                language="sql",
                metadata={"sql_kind": kind},
            )
        )
    return symbols


# ---------------------------------------------------------------------------
# Markdown / MDX
# ---------------------------------------------------------------------------


_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def _index_markdown(path: Path, text: str) -> list[Symbol]:
    symbols: list[Symbol] = [
        Symbol(
            name=path.stem,
            kind="module",
            file=str(path),
            start_line=1,
            end_line=max(1, text.count("\n") + 1),
            language="markdown",
        )
    ]
    for i, line in enumerate(text.splitlines(), start=1):
        if m := _MD_HEADING_RE.match(line):
            symbols.append(
                Symbol(
                    name=m.group(2).strip(),
                    kind="section",
                    file=str(path),
                    start_line=i,
                    end_line=i,
                    language="markdown",
                    metadata={"level": str(len(m.group(1)))},
                )
            )
    return symbols


__all__ = [
    "Symbol",
    "SymbolKind",
    "index_file",
    "index_workspace",
]
