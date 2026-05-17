"""Policy enforcement helpers for :class:`CodebaseMCPTool` instances.

The headline constraints (AGENTS rule 22 / 26 / 27 compatible):

- ``enforce_path_inside_workspace`` — every path argument must resolve
  inside ``ctx.workspace_root`` (or the configured fallback). Any
  attempt to read ``/etc/passwd``, escape with ``../``, or follow a
  symlink outside the tree raises :class:`MCPPolicyError`.
- ``enforce_no_secret_globs`` — common secret filenames (``.env``,
  ``*.pem``, ``secrets/*``, ``id_rsa*``, ``*.key``) are denied at
  policy time before any read happens.
- ``enforce_required_scopes`` — default scope check baked into the
  base class.
"""
from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Iterable

from aqp.codebase.mcp.base import MCPPolicyError, MCPToolContext

logger = logging.getLogger(__name__)


# Default secret patterns denied at policy time. Operators can extend
# via ``settings.codebase_secret_globs`` (CSV).
_DEFAULT_SECRET_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_rsa.*",
    "secrets/*",
    "*/secrets/*",
    "credentials.json",
    "*.kubeconfig",
)


def _workspace_root(ctx: MCPToolContext) -> Path:
    if ctx.workspace_root:
        root = Path(ctx.workspace_root)
    else:
        try:
            from aqp.config import settings

            root = Path(
                str(getattr(settings, "codebase_workspace_root", "") or "").strip()
                or Path.cwd()
            )
        except Exception:  # noqa: BLE001
            root = Path.cwd()
    return root.resolve()


def _secret_globs() -> tuple[str, ...]:
    try:
        from aqp.config import settings

        extra = str(getattr(settings, "codebase_secret_globs", "") or "").strip()
        if extra:
            return _DEFAULT_SECRET_GLOBS + tuple(g.strip() for g in extra.split(",") if g.strip())
    except Exception:  # noqa: BLE001
        pass
    return _DEFAULT_SECRET_GLOBS


def enforce_required_scopes(
    ctx: MCPToolContext, required: Iterable[str]
) -> None:
    """Reject calls missing any of the ``required`` scopes."""
    granted = set(ctx.granted_scopes or ())
    missing = [scope for scope in required if scope not in granted]
    if missing:
        raise MCPPolicyError(
            f"missing required scope(s) {missing!r} (granted: {sorted(granted)})"
        )


def enforce_path_inside_workspace(ctx: MCPToolContext, path: str | os.PathLike[str]) -> Path:
    """Resolve ``path`` and verify it sits inside the workspace root.

    Returns the resolved :class:`Path`. Raises :class:`MCPPolicyError`
    when the path escapes the root (including via symlink traversal).
    """
    root = _workspace_root(ctx)
    raw = Path(path)
    # Resolve relative paths against the workspace root, never the
    # current working directory (the codebase tool may be invoked
    # from anywhere — stdio, Celery, FastAPI, …).
    if not raw.is_absolute():
        raw = (root / raw)
    try:
        resolved = raw.resolve()
    except FileNotFoundError:
        resolved = raw.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise MCPPolicyError(
            f"path {str(raw)!r} escapes workspace root {str(root)!r}"
        ) from exc
    return resolved


def enforce_no_secret_globs(ctx: MCPToolContext, path: str | os.PathLike[str]) -> None:
    """Reject filenames matching any of the configured secret globs."""
    p = Path(path)
    rel = p.name
    # Match either the basename or the full posix-style path against
    # each glob so patterns like ``secrets/*`` work.
    full = str(p).replace("\\", "/")
    for glob in _secret_globs():
        if fnmatch.fnmatchcase(rel, glob) or fnmatch.fnmatchcase(full, glob):
            raise MCPPolicyError(
                f"path {str(p)!r} matches secret glob {glob!r}"
            )


def enforce_read_only_for_session(
    ctx: MCPToolContext, *, mutates: bool
) -> None:
    """Reject mutating tools without ``code:write`` scope."""
    if not mutates:
        return
    if "code:write" not in (ctx.granted_scopes or ()):
        raise MCPPolicyError(
            "mutating codebase tools require 'code:write' scope on the session"
        )


__all__ = [
    "enforce_no_secret_globs",
    "enforce_path_inside_workspace",
    "enforce_read_only_for_session",
    "enforce_required_scopes",
]
