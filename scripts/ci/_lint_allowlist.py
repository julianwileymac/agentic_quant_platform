"""Shared allowlist loader for the Phase 0 lint scripts.

Each lint script under ``scripts/ci/`` may declare a per-lint allowlist
file at ``scripts/ci/allowlists/<lint_name>.txt`` containing one
repository-relative path per line. Blank lines and lines starting with
``#`` are ignored. Lines may carry a trailing ``# comment`` describing
the deadline / TODO marker (e.g. ``# TODO(phase-1): remove by 2026-08-15``).

Allowlists are an escape hatch — they should never be empty for long.
Every entry MUST carry a removal deadline in its trailing comment.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ALLOWLIST_DIR = REPO_ROOT / "scripts" / "ci" / "allowlists"


def normalise_path(path: str | os.PathLike[str]) -> str:
    """Return a forward-slash POSIX-style relative path used in allowlists.

    On Windows the script may be invoked with backslashes; the
    canonical form across the repo is ``a/b/c.py`` so the allowlist
    file can be edited consistently.
    """
    text = str(path).replace(os.sep, "/").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def load_allowlist(lint_name: str) -> set[str]:
    """Return the allowlisted relative paths for ``lint_name``.

    Returns an empty set when no allowlist file is present.
    """
    target = ALLOWLIST_DIR / f"{lint_name}.txt"
    if not target.is_file():
        return set()
    entries: set[str] = set()
    for raw in target.read_text(encoding="utf-8").splitlines():
        # Strip trailing comment but keep the path itself intact.
        stripped = raw.split("#", 1)[0].strip()
        if not stripped:
            continue
        entries.add(normalise_path(stripped))
    return entries


def filter_violations(
    violations: Iterable[tuple[str, str]], lint_name: str
) -> list[tuple[str, str]]:
    """Drop violations whose path is allowlisted for ``lint_name``.

    Each ``violation`` is a ``(path, message)`` tuple. ``path`` may be
    absolute or repo-relative; comparison is done against the
    normalised path.
    """
    allowed = load_allowlist(lint_name)
    if not allowed:
        return list(violations)
    out: list[tuple[str, str]] = []
    for path, message in violations:
        rel = normalise_path(_to_repo_relative(path))
        if rel in allowed:
            continue
        out.append((path, message))
    return out


def _to_repo_relative(path: str | os.PathLike[str]) -> str:
    """Best-effort conversion of an absolute or relative path to repo-relative."""
    p = Path(str(path))
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except Exception:
        return str(p)


__all__ = [
    "ALLOWLIST_DIR",
    "REPO_ROOT",
    "filter_violations",
    "load_allowlist",
    "normalise_path",
]
