"""Per-request runtime context for the tenancy layer (Workstream F).

Stores the active :class:`aqp.auth.context.RequestContext` in a
``contextvars.ContextVar`` keyed by the OS thread / asyncio task. The
ASGI middleware in :mod:`aqp.api.middleware.tenancy_middleware`
populates it on every request; tenancy strategies read it to derive
``workspace_id`` for ``SET LOCAL`` GUC writes.

We deliberately store the platform's existing :class:`RequestContext`
rather than introducing a separate type — that way nothing else in
the codebase has to learn a new shape.

PEP 567 guarantees ``ContextVar`` propagates across
``asyncio.create_task``; :mod:`ThreadPoolExecutor` workers must use
``contextvars.copy_context().run(fn)`` to inherit it. We document this
sharp edge in the module docstring so reviewers don't break it.
"""
from __future__ import annotations

import contextvars
from typing import Any


_RUNTIME_CONTEXT: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "aqp_tenancy_runtime_context", default=None
)


def set_runtime_context(ctx: Any | None) -> contextvars.Token:
    """Set the active runtime context; returns the reset token."""
    return _RUNTIME_CONTEXT.set(ctx)


def reset_runtime_context(token: contextvars.Token) -> None:
    """Restore the prior context (use the token from :func:`set_runtime_context`)."""
    _RUNTIME_CONTEXT.reset(token)


def get_runtime_context() -> Any | None:
    """Return the active context, or ``None`` when none is set."""
    return _RUNTIME_CONTEXT.get()


__all__ = [
    "get_runtime_context",
    "reset_runtime_context",
    "set_runtime_context",
]
