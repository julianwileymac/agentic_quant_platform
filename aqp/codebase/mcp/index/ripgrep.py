"""ripgrep-backed lexical search for the codebase MCP.

Uses the host's ``rg`` binary when available (fast, robust, gitignore
aware); falls back to a pure-Python recursive scan so tests can run
on environments without ripgrep installed.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LexicalMatch:
    file: str
    line: int
    column: int
    text: str
    score: float = 1.0


def _rg_bin() -> str | None:
    try:
        from aqp.config import settings

        explicit = (str(getattr(settings, "codebase_ripgrep_path", "") or "")).strip()
        if explicit:
            return explicit
    except Exception:  # noqa: BLE001
        pass
    return shutil.which("rg")


def ripgrep_search(
    *,
    root: str | Path,
    query: str,
    include_globs: Iterable[str] | None = None,
    case_insensitive: bool = True,
    max_results: int = 200,
) -> list[LexicalMatch]:
    """Run a literal search over ``root`` and return up to ``max_results``."""
    root_path = Path(root).resolve()
    if not root_path.is_dir() or not query:
        return []

    rg = _rg_bin()
    if rg:
        return _rg_search(
            rg,
            root_path,
            query,
            include_globs,
            case_insensitive,
            max_results,
        )
    return _python_search(
        root_path, query, include_globs, case_insensitive, max_results
    )


def _rg_search(
    rg: str,
    root: Path,
    query: str,
    include_globs: Iterable[str] | None,
    case_insensitive: bool,
    max_results: int,
) -> list[LexicalMatch]:
    args = [
        rg,
        "--no-heading",
        "--line-number",
        "--column",
        "--color",
        "never",
        "--max-count",
        str(int(max_results)),
    ]
    if case_insensitive:
        args.append("--ignore-case")
    for pat in include_globs or ():
        args.extend(["--glob", pat])
    args.extend(["--", query, str(root)])
    try:
        out = subprocess.run(
            args, capture_output=True, text=True, timeout=15, check=False
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("ripgrep failed: %s", exc)
        return []
    matches: list[LexicalMatch] = []
    for line in out.stdout.splitlines():
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        path, lineno, col, text = parts
        try:
            matches.append(
                LexicalMatch(
                    file=path,
                    line=int(lineno),
                    column=int(col),
                    text=text,
                )
            )
        except ValueError:
            continue
        if len(matches) >= max_results:
            break
    return matches


def _python_search(
    root: Path,
    query: str,
    include_globs: Iterable[str] | None,
    case_insensitive: bool,
    max_results: int,
) -> list[LexicalMatch]:
    flags = re.IGNORECASE if case_insensitive else 0
    pattern = re.compile(re.escape(query), flags)
    globs = tuple(
        include_globs or ("*.py", "*.ts", "*.tsx", "*.md", "*.mdx", "*.yaml", "*.yml")
    )
    matches: list[LexicalMatch] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not any(path.match(g) for g in globs):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            m = pattern.search(line)
            if not m:
                continue
            matches.append(
                LexicalMatch(
                    file=str(path),
                    line=i,
                    column=m.start() + 1,
                    text=line.rstrip(),
                )
            )
            if len(matches) >= max_results:
                return matches
    return matches


__all__ = ["LexicalMatch", "ripgrep_search"]
