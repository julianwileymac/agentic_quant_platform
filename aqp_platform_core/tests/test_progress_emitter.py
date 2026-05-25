"""Contract tests for the :class:`ProgressEmitter` protocol + adapters."""
from __future__ import annotations

import logging

import pytest

from aqp_platform_core.runtime.progress import (
    NullProgressEmitter,
    ProgressEmitter,
    StructuredLogProgressEmitter,
)


def test_null_emitter_satisfies_protocol() -> None:
    emitter = NullProgressEmitter()
    assert isinstance(emitter, ProgressEmitter)
    emitter.emit("t", "stage", "hello")
    emitter.emit_done("t", {"ok": True})
    emitter.emit_error("t", "boom")
    assert emitter.emitted == 3


def test_structured_emitter_writes_frame(caplog: pytest.LogCaptureFixture) -> None:
    emitter = StructuredLogProgressEmitter(logger_name="aqp.test.progress")
    with caplog.at_level(logging.INFO, logger="aqp.test.progress"):
        emitter.emit("task-1", "init", "starting", custom="payload")
        emitter.emit_done("task-1", {"result": 42})
        emitter.emit_error("task-1", "kaboom")
    msgs = "\n".join(rec.message for rec in caplog.records)
    assert "task_id=task-1" in msgs
    assert "stage=init" in msgs
    assert "stage=done" in msgs
    assert "stage=error" in msgs


def test_emitter_tolerates_context_object() -> None:
    class FakeCtx:
        user_id = "auth0|abc"
        org_id = "acme"
        workspace_id = None
        project_id = "alpha"
        request_id = "req-1"

    emitter = StructuredLogProgressEmitter(logger_name="aqp.test.progress2")
    # Must not raise.
    emitter.emit("t", "stage", "msg", context=FakeCtx())


def test_emitter_swallows_failures() -> None:
    class Boom:
        def to_finops_extras(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("bad context")

    emitter = StructuredLogProgressEmitter(logger_name="aqp.test.progress3")
    # Must not raise even though the context blows up.
    emitter.emit("t", "stage", "msg", context=Boom())
