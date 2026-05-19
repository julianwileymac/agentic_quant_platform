"""Audit ledger writer — append-only ``workload_runs`` rows (AGENTS rule 45).

Writes both to structured logging (always) and to an optional JSONL file
when ``AQP_CP_AUDIT_LOG_PATH`` is set. The Postgres-backed writer is a
follow-up PR; the API surface stays stable.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aqp_cp.models import WorkloadAction, WorkloadRun, WorkloadRunStatus
from aqp_cp.settings import get_settings

logger = logging.getLogger("aqp_cp.audit")

_LOCK = threading.Lock()


def new_run_id() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


def start_run(
    *,
    action: WorkloadAction,
    provider: str,
    target: str,
    user_id: str,
    request_id: str | None = None,
    org_id: str | None = None,
    workspace_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> WorkloadRun:
    """Create + persist a WorkloadRun in PENDING state BEFORE the provider call.

    Per AGENTS rule 45, the full audit context is recorded BEFORE the
    provider executes so a crash mid-call still leaves a trail.
    """
    run = WorkloadRun(
        run_id=new_run_id(),
        started_at=now(),
        status=WorkloadRunStatus.PENDING,
        action=action,
        provider=provider,
        target=target,
        user_id=user_id,
        request_id=request_id,
        org_id=org_id,
        workspace_id=workspace_id,
        payload=_redact_payload(payload or {}),
    )
    _persist(run, phase="start")
    return run


def finish_run(
    run: WorkloadRun,
    *,
    status: WorkloadRunStatus,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> WorkloadRun:
    """Update + persist the WorkloadRun after the provider call completes."""
    finished_at = now()
    duration_ms = (finished_at - run.started_at).total_seconds() * 1000.0
    updated = run.model_copy(
        update={
            "status": status,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "result": result or {},
            "error": error,
        }
    )
    _persist(updated, phase="finish")
    return updated


def _persist(run: WorkloadRun, *, phase: str) -> None:
    """Emit a structured log line + append to the JSONL file when configured."""
    body = run.model_dump(mode="json")
    logger.info("workload_run phase=%s %s", phase, json.dumps(body, default=str))

    settings = get_settings()
    if not settings.audit_log_path:
        return
    path = Path(settings.audit_log_path)
    try:
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(body, default=str))
                fh.write("\n")
    except OSError as exc:  # noqa: BLE001
        logger.warning("audit log write failed (path=%s): %s", path, exc)


_SECRET_HINTS = ("password", "secret", "token", "key", "credential", "private")


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort redaction of secret-looking keys in the audit payload."""
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        lk = str(key).lower()
        if any(hint in lk for hint in _SECRET_HINTS):
            redacted[key] = "<redacted>"
        elif isinstance(value, dict):
            redacted[key] = _redact_payload(value)
        else:
            redacted[key] = value
    return redacted


__all__ = ["finish_run", "new_run_id", "now", "start_run"]
