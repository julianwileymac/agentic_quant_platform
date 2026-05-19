"""Phase 3b control-plane maturation tests — SecureTask Celery base.

Asserts that:

- ``context_to_headers`` round-trips through ``headers_to_context``.
- An empty / missing header dict produces a sensible default context
  rather than raising.
- The ``SecureTask.__call__`` wrapper binds the contextvar correctly
  for the body and resets it after return / exception.
- The ``before_task_publish`` signal stamps the active
  ``RequestContext`` onto task headers under the ``x-aqp-rctx`` key.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aqp.auth.context import RequestContext
from aqp.auth.contextvars import bind_context, current_request_context
from aqp.tasks.secure_task import (
    RCTX_HEADER_KEY,
    SecureTask,
    context_to_headers,
    headers_to_context,
)


# ---------------------------------------------------------------------------
# Header round-trip
# ---------------------------------------------------------------------------


class TestContextHeaderRoundTrip:
    def test_full_context_round_trips(self) -> None:
        ctx = RequestContext(
            user_id="user-1",
            org_id="org-7",
            workspace_id="ws-42",
            project_id="proj-3",
            role="admin",
            live_control=True,
            experiment_id="exp-9",
        )
        headers = context_to_headers(ctx)
        rebuilt = headers_to_context(headers)

        assert rebuilt.user_id == "user-1"
        assert rebuilt.org_id == "org-7"
        assert rebuilt.workspace_id == "ws-42"
        assert rebuilt.project_id == "proj-3"
        assert rebuilt.role == "admin"
        assert rebuilt.live_control is True
        assert rebuilt.experiment_id == "exp-9"

    def test_partial_context_round_trips(self) -> None:
        ctx = RequestContext(user_id="user-only")
        rebuilt = headers_to_context(context_to_headers(ctx))
        assert rebuilt.user_id == "user-only"
        assert rebuilt.workspace_id is None
        assert rebuilt.org_id is None

    def test_empty_headers_returns_default_context(self) -> None:
        rebuilt = headers_to_context(None)
        assert rebuilt.user_id  # default has a populated user_id
        rebuilt2 = headers_to_context({})
        assert rebuilt2.user_id

    def test_malformed_headers_does_not_raise(self) -> None:
        # Garbage in -> default context out, never an exception
        rebuilt = headers_to_context({"user_id": ["not", "a", "string"]})
        assert rebuilt is not None  # falls back to default


# ---------------------------------------------------------------------------
# SecureTask binding
# ---------------------------------------------------------------------------


class TestSecureTaskBinding:
    """The base class binds the contextvar before run, resets after."""

    def _build_task(self, headers: dict[str, Any] | None) -> SecureTask:
        """Construct a minimal SecureTask instance with a faked request."""
        task = SecureTask()
        task.name = "test.secure_task.fake"
        request = MagicMock()
        request.id = "task-id-1"
        request.headers = headers or {}
        # celery.Task.request is normally read-only; substitute a thin proxy.
        task.request_stack = MagicMock()
        task.request_stack.top = request
        # celery.Task exposes self.request via a property. Patch the attr.
        type(task).request = property(lambda self: request)  # type: ignore[assignment]
        return task

    def test_call_binds_context_for_body(self) -> None:
        ctx = RequestContext(user_id="user-bound", workspace_id="ws-bound")
        headers = {RCTX_HEADER_KEY: context_to_headers(ctx)}
        task = self._build_task(headers)

        observed: dict[str, RequestContext | None] = {"ctx": None}

        def fake_run(self_inner, *args, **kwargs):
            observed["ctx"] = current_request_context.get()
            return "ok"

        # celery.Task.__call__ delegates to ``run`` via super(); patch the
        # `run` attribute so we observe what the body sees.
        task.run = fake_run.__get__(task, SecureTask)  # type: ignore[assignment]

        result = task()
        assert result == "ok"
        # Inside the body, the contextvar held our identity
        assert observed["ctx"] is not None
        assert observed["ctx"].user_id == "user-bound"
        assert observed["ctx"].workspace_id == "ws-bound"
        # After the body, the contextvar was reset
        assert current_request_context.get() is None

    def test_call_resets_on_exception(self) -> None:
        ctx = RequestContext(user_id="user-failing")
        headers = {RCTX_HEADER_KEY: context_to_headers(ctx)}
        task = self._build_task(headers)

        def boom(self_inner, *args, **kwargs):
            raise RuntimeError("intentional")

        task.run = boom.__get__(task, SecureTask)  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="intentional"):
            task()
        # Even on exception, the contextvar is reset
        assert current_request_context.get() is None

    def test_security_ctx_attribute_is_set(self) -> None:
        ctx = RequestContext(user_id="user-attr", workspace_id="ws-attr")
        headers = {RCTX_HEADER_KEY: context_to_headers(ctx)}
        task = self._build_task(headers)

        def fake_run(self_inner, *args, **kwargs):
            return self_inner.security_ctx

        task.run = fake_run.__get__(task, SecureTask)  # type: ignore[assignment]
        result = task()
        assert isinstance(result, RequestContext)
        assert result.user_id == "user-attr"
        assert result.workspace_id == "ws-attr"


# ---------------------------------------------------------------------------
# before_task_publish stamping
# ---------------------------------------------------------------------------


class TestBeforeTaskPublishStamps:
    """The signal handler in ``aqp.tasks.celery_app`` writes the rctx header."""

    def setup_method(self) -> None:
        # Reset the contextvar to a known state before each test
        current_request_context.set(None)

    def test_active_context_lands_in_headers(self) -> None:
        from aqp.tasks.celery_app import _attach_request_context_headers

        ctx = RequestContext(
            user_id="dispatcher-1",
            workspace_id="ws-publish",
        )
        token = bind_context(ctx)
        try:
            headers: dict[str, Any] = {}
            _attach_request_context_headers(
                sender="test.task", headers=headers, body=None
            )
            stamped = headers.get(RCTX_HEADER_KEY)
            assert isinstance(stamped, dict)
            assert stamped["user_id"] == "dispatcher-1"
            assert stamped["workspace_id"] == "ws-publish"
        finally:
            current_request_context.reset(token)

    def test_no_active_context_skips_header(self) -> None:
        from aqp.tasks.celery_app import _attach_request_context_headers

        # No context bound -> handler is a no-op
        headers: dict[str, Any] = {}
        _attach_request_context_headers(
            sender="test.task", headers=headers, body=None
        )
        assert RCTX_HEADER_KEY not in headers

    def test_caller_supplied_user_id_wins(self) -> None:
        """An explicit RCTX header on the dispatch site takes precedence."""
        from aqp.tasks.celery_app import _attach_request_context_headers

        ctx = RequestContext(user_id="background-user")
        token = bind_context(ctx)
        try:
            headers: dict[str, Any] = {
                RCTX_HEADER_KEY: {"user_id": "explicit-override"}
            }
            _attach_request_context_headers(
                sender="test.task", headers=headers, body=None
            )
            stamped = headers.get(RCTX_HEADER_KEY)
            assert isinstance(stamped, dict)
            assert stamped["user_id"] == "explicit-override"
        finally:
            current_request_context.reset(token)


__all__: list[str] = []
