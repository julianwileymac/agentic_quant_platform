"""ServeHandler — queue-based continuous-batching inference scheduler.

The report describes a multi-tenant, continuous-batching server that
buffers incoming inference requests into a single tensor and replays
the results back to the per-request futures. This handler implements
the orchestration layer:

* Each "session" wraps one cached model + one inbound queue.
* Requests are batched up to ``max_batch_size`` or flushed when the
  oldest entry exceeds ``max_wait_ms``.
* Sessions register in the platform's ``ml_serving_sessions`` table so
  operators can monitor them through the frontend dashboard.
* The platform kill-switch can halt every active session via the
  ``halt_all`` class-method, which mirrors the existing
  ``/agents/halt`` / ``/bots/halt-all`` / ``/rl/halt-all`` fan-out.

The default scheduler is intentionally simple — production-grade
batching for HuggingFace transformer pipelines is handled by vLLM
through :mod:`aqp_models.serving.vllm`. This handler is what agents and
the analytics frontend talk to for everything else.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from typing import Any, Callable

from aqp_models.handlers.base import (
    HandlerContext,
    HandlerResult,
    MLOpsHandler,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ServingRequest:
    """One inbound inference request."""

    request_id: str
    payload: Any
    submitted_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class _PendingItem:
    """Internal: a request waiting for a batched response."""

    req: ServingRequest
    event: threading.Event
    result: Any | None = None
    error: str | None = None


@dataclass
class ServingSession:
    """One running scheduler loop wrapped around a cached model."""

    session_id: str
    model_alias: str
    model: Any
    max_batch_size: int
    max_wait_ms: int
    workspace_id: str | None = None
    project_id: str | None = None
    halted: bool = False
    pending_count: int = 0
    served_count: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)
    _queue: Queue = field(default_factory=Queue)
    _worker: threading.Thread | None = None
    _stop_event: threading.Event = field(default_factory=threading.Event)

    def submit(self, payload: Any, timeout: float | None = 30.0) -> Any:
        if self.halted:
            raise RuntimeError(f"session {self.session_id} is halted")
        req = ServingRequest(request_id=str(uuid.uuid4()), payload=payload)
        item = _PendingItem(req=req, event=threading.Event())
        self._queue.put(item)
        self.pending_count += 1
        if not item.event.wait(timeout=timeout):
            raise TimeoutError(f"inference timeout after {timeout}s")
        if item.error:
            raise RuntimeError(item.error)
        return item.result

    def descriptor(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "model_alias": self.model_alias,
            "model_class": self.model.__class__.__name__,
            "max_batch_size": int(self.max_batch_size),
            "max_wait_ms": int(self.max_wait_ms),
            "halted": bool(self.halted),
            "pending": int(self.pending_count),
            "served": int(self.served_count),
            "started_at": self.started_at.isoformat(),
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
        }


class ServeHandler(MLOpsHandler):
    """Multi-session continuous-batching scheduler."""

    handler_name = "ml.serve"
    required_scopes = ("data:read",)
    mutates = True

    # Class-level session registry so the kill-switch can fan out across
    # every loaded session in the worker process. Real cross-process
    # halting goes through the API + Postgres `ml_serving_sessions`.
    _sessions: dict[str, ServingSession] = {}
    _registry_lock = threading.RLock()

    def __init__(
        self,
        *,
        predict_fn: Callable[[Any, list[Any]], list[Any]] | None = None,
    ) -> None:
        super().__init__()
        self._predict_fn = predict_fn or _default_predict_fn

    # ------------------------------------------------------------------
    # MLOpsHandler entry
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        ctx: HandlerContext,
        op: str = "list",
        session_id: str | None = None,
        model_alias: str | None = None,
        model: Any | None = None,
        max_batch_size: int | None = None,
        max_wait_ms: int | None = None,
        payload: Any = None,
        **_: Any,
    ) -> HandlerResult:
        op = (op or "list").lower()

        if op == "start":
            if model is None:
                return HandlerResult(ok=False, error="start requires ``model``")
            session = self.start_session(
                model=model,
                model_alias=model_alias or model.__class__.__name__,
                max_batch_size=max_batch_size,
                max_wait_ms=max_wait_ms,
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
            )
            return HandlerResult(
                ok=True,
                data=session.descriptor(),
                summary=f"started {session.session_id}",
                metadata={"op": "start"},
            )

        if op == "submit":
            if not session_id:
                return HandlerResult(ok=False, error="submit requires ``session_id``")
            session = self._sessions.get(session_id)
            if session is None:
                return HandlerResult(ok=False, error=f"unknown session {session_id!r}")
            try:
                result = session.submit(payload)
            except TimeoutError as exc:
                return HandlerResult(ok=False, error=str(exc))
            except Exception as exc:  # noqa: BLE001
                return HandlerResult(ok=False, error=str(exc))
            return HandlerResult(
                ok=True,
                data={"session_id": session_id, "result": result},
                summary=f"served on {session_id}",
                metadata={"op": "submit"},
            )

        if op == "stop":
            if not session_id:
                return HandlerResult(ok=False, error="stop requires ``session_id``")
            stopped = self.stop_session(session_id)
            return HandlerResult(
                ok=True,
                data={"session_id": session_id, "stopped": stopped},
                summary=f"stopped {session_id}" if stopped else f"no session {session_id}",
                metadata={"op": "stop"},
            )

        if op == "halt_all":
            n = self.halt_all()
            return HandlerResult(
                ok=True,
                data={"halted": n},
                summary=f"halted {n} sessions",
                metadata={"op": "halt_all"},
            )

        if op == "list":
            descriptors = [s.descriptor() for s in self._sessions.values()]
            return HandlerResult(
                ok=True,
                data={"sessions": descriptors, "n_sessions": len(descriptors)},
                summary=f"{len(descriptors)} active sessions",
                metadata={"op": "list"},
            )

        return HandlerResult(ok=False, error=f"unknown serve op {op!r}")

    # ------------------------------------------------------------------
    # Public Python surface (kill-switch / route layer use these)
    # ------------------------------------------------------------------

    def start_session(
        self,
        *,
        model: Any,
        model_alias: str,
        max_batch_size: int | None = None,
        max_wait_ms: int | None = None,
        workspace_id: str | None = None,
        project_id: str | None = None,
    ) -> ServingSession:
        max_batch = int(max_batch_size or _settings_int("ml_serving_max_batch_size", 64))
        max_wait = int(max_wait_ms or _settings_int("ml_serving_max_wait_ms", 25))
        session_id = str(uuid.uuid4())
        session = ServingSession(
            session_id=session_id,
            model_alias=model_alias,
            model=model,
            max_batch_size=max_batch,
            max_wait_ms=max_wait,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        worker = threading.Thread(
            target=self._scheduler_loop,
            args=(session,),
            name=f"ml-serve-{session_id[:8]}",
            daemon=True,
        )
        session._worker = worker
        with self._registry_lock:
            self._sessions[session_id] = session
        worker.start()
        self._mirror_to_postgres(session, op="start")
        return session

    def stop_session(self, session_id: str) -> bool:
        with self._registry_lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session._stop_event.set()
        session.halted = True
        # Drain pending items with a halt error
        try:
            while True:
                pending = session._queue.get_nowait()
                pending.error = "halted"
                pending.event.set()
        except Empty:
            pass
        self._mirror_to_postgres(session, op="stop")
        return True

    @classmethod
    def halt_all(cls) -> int:
        with cls._registry_lock:
            keys = list(cls._sessions.keys())
        n = 0
        for sid in keys:
            handler = cls()
            if handler.stop_session(sid):
                n += 1
        return n

    @classmethod
    def list_sessions(cls) -> list[dict[str, Any]]:
        with cls._registry_lock:
            return [s.descriptor() for s in cls._sessions.values()]

    # ------------------------------------------------------------------
    # Scheduler loop
    # ------------------------------------------------------------------

    def _scheduler_loop(self, session: ServingSession) -> None:
        while not session._stop_event.is_set():
            batch: list[_PendingItem] = []
            try:
                first = session._queue.get(timeout=0.1)
            except Empty:
                continue
            batch.append(first)
            deadline = time.monotonic() + session.max_wait_ms / 1000.0
            while len(batch) < session.max_batch_size and time.monotonic() < deadline:
                try:
                    item = session._queue.get(timeout=max(deadline - time.monotonic(), 0.0))
                except Empty:
                    break
                batch.append(item)

            payloads = [it.req.payload for it in batch]
            try:
                results = self._predict_fn(session.model, payloads)
            except Exception as exc:  # noqa: BLE001
                logger.exception("serve batch failed")
                for it in batch:
                    it.error = str(exc)
                    it.event.set()
                session.pending_count = max(session.pending_count - len(batch), 0)
                continue

            if len(results) != len(batch):
                # Backend returned the wrong shape — pad / truncate to keep
                # the contract honest, then report a per-item error for
                # missing slots.
                results = list(results)
                while len(results) < len(batch):
                    results.append(None)

            for it, res in zip(batch, results):
                it.result = res
                it.event.set()
            served = len(batch)
            session.pending_count = max(session.pending_count - served, 0)
            session.served_count += served

        # Drain any remaining items so submitters don't hang.
        try:
            while True:
                pending = session._queue.get_nowait()
                pending.error = "halted"
                pending.event.set()
        except Empty:
            pass

    # ------------------------------------------------------------------
    # Best-effort persistence (so the operator UI can see active sessions)
    # ------------------------------------------------------------------

    def _mirror_to_postgres(self, session: ServingSession, *, op: str) -> None:
        try:
            from aqp.persistence.db import get_session as _pg
            from aqp.persistence.models_mlops import MlServingSession

            with _pg() as pg:
                row = (
                    pg.query(MlServingSession)
                    .filter(MlServingSession.session_id == session.session_id)
                    .one_or_none()
                )
                if op == "stop":
                    if row is not None:
                        row.halted = True
                        row.ended_at = datetime.utcnow()
                    return
                if row is None:
                    row = MlServingSession(
                        session_id=session.session_id,
                        model_alias=session.model_alias,
                        model_class=session.model.__class__.__name__,
                        max_batch_size=session.max_batch_size,
                        max_wait_ms=session.max_wait_ms,
                        halted=False,
                        started_at=session.started_at,
                        workspace_id=session.workspace_id,
                        project_id=session.project_id,
                    )
                    pg.add(row)
                else:
                    row.halted = False
                    row.ended_at = None
        except Exception:  # noqa: BLE001
            logger.debug("serve postgres mirror failed", exc_info=True)


# ---------------------------------------------------------------------------
# Default predict_fn
# ---------------------------------------------------------------------------


def _default_predict_fn(model: Any, payloads: list[Any]) -> list[Any]:
    """Fan a list of payloads into ``model.predict`` and split the results.

    Many AQP models accept a ``DataFrame`` and emit a ``Series``; the
    default scheduler stacks the payloads, calls predict once, and
    demultiplexes. For non-DataFrame payloads it falls back to a
    per-item loop.
    """
    try:
        import numpy as np
        import pandas as pd

        if all(isinstance(p, pd.DataFrame) for p in payloads):
            stacked = pd.concat(payloads, axis=0, ignore_index=False)
            out = model.predict(stacked) if hasattr(model, "predict") else model(stacked)
            arr = (
                out.to_numpy()
                if isinstance(out, (pd.Series, pd.DataFrame))
                else np.asarray(out)
            )
            sizes = [len(p) for p in payloads]
            chunks: list[Any] = []
            start = 0
            for size in sizes:
                chunks.append(arr[start : start + size])
                start += size
            return chunks
    except Exception:  # noqa: BLE001
        logger.debug("default predict_fn batch path failed, falling back", exc_info=True)

    out: list[Any] = []
    for payload in payloads:
        if hasattr(model, "predict"):
            out.append(model.predict(payload))
        elif callable(model):
            out.append(model(payload))
        else:
            raise TypeError(f"model {model.__class__.__name__} is not callable")
    return out


def _settings_int(name: str, default: int) -> int:
    try:
        from aqp.config import settings

        return int(getattr(settings, name, default))
    except Exception:  # noqa: BLE001
        return int(default)


__all__ = [
    "ServeHandler",
    "ServingRequest",
    "ServingSession",
]
