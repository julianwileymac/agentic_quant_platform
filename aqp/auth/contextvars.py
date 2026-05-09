"""Async-safe context variables carrying the active :class:`RequestContext`.

The FastAPI dep :func:`aqp.auth.deps.current_context` populates the
:data:`current_request_context` ContextVar on every request so deeply
nested chokepoints (the Iceberg wrapper, the LedgerWriter, agent and bot
runtimes, RAG readers/writers, MCP tool bridges) can re-hydrate the
caller's identity without threading a positional ``ctx`` argument
through every function signature.

For Celery tasks the publisher copies the context into task headers and
the worker re-installs it via :func:`bind_context` inside the task
body. This mirrors how OpenTelemetry propagates spans across worker
boundaries — same idea, smaller payload.

Usage:

.. code-block:: python

    from aqp.auth.contextvars import current_request_context, bind_context

    # FastAPI dep (already wired by aqp.auth.deps)
    bind_context(ctx)

    # Anywhere downstream
    ctx = current_request_context.get()
    if ctx is not None:
        iceberg_catalog.append_arrow(table, df, context=ctx, shared=False)

The ContextVar default is ``None`` so callers must defensively branch on
that case (callable from CLIs / unit tests that never enter the FastAPI
request lifecycle).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from aqp.auth.context import RequestContext


current_request_context: ContextVar["RequestContext | None"] = ContextVar(
    "aqp_current_request_context", default=None
)


def bind_context(ctx: "RequestContext | None") -> object:
    """Install *ctx* as the active context, returning a reset token.

    The reset token can be passed to :meth:`ContextVar.reset` to restore
    the previous value (e.g. inside Celery task teardown).
    """
    return current_request_context.set(ctx)


@contextmanager
def use_context(ctx: "RequestContext | None") -> Iterator["RequestContext | None"]:
    """Temporarily install *ctx* as the active context.

    Restores the previous binding on exit, even if the body raises.
    """
    token = current_request_context.set(ctx)
    try:
        yield ctx
    finally:
        current_request_context.reset(token)


def get_context_or_default() -> "RequestContext":
    """Return the active context, falling back to the local-first default.

    Convenience for chokepoints that always need *something* — e.g.
    ``iceberg_catalog.append_arrow`` would rather stamp the default
    workspace than skip the column entirely.
    """
    from aqp.auth.context import default_context

    ctx = current_request_context.get()
    return ctx if ctx is not None else default_context()


__all__ = [
    "bind_context",
    "current_request_context",
    "get_context_or_default",
    "use_context",
]
