"""TerraformRun-specific HTTP audit sink.

The shared :class:`aqp_cp.services.http_audit_sink.HttpAuditSink` posts
:class:`WorkloadRun` rows to ``/_internal/audit/workload-runs``; that
keeps the cross-runtime audit ledger consistent but loses the rich
shape of a :class:`TerraformRunResult` (plan summary, exit code,
spec hash, halt reason). This sink emits a sibling row to
``/_internal/audit/terraform-runs`` so the monolith's
``TerraformRun`` ORM table keeps every column the historic in-process
runtime wrote — most importantly the ``plan_summary_json``,
``exit_code``, ``halted``, ``policy_check_result``, and ``error``
fields the operator UI inspects after every apply.

Per AGENTS rule 42 footnote: *"The CP-side TerraformRuntime persists
``terraform_runs`` rows via :class:`aqp_cp.audit.HttpAuditSink` ->
monolith ``/_internal/audit/terraform-runs`` so the Postgres ledger
stays the single source of truth even when the executor runs
out-of-process."*

Failure mode: this sink degrades to log-only on any HTTP error so the
runtime contract (audit-side never raises) holds even when the
monolith is unreachable.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from aqp_platform_core.models.terraform import (
    TerraformRunKind,
    TerraformRunResult,
    TerraformStackSpec,
)

logger = logging.getLogger(__name__)


class TerraformAuditSink(Protocol):
    """Audit-sink protocol the :class:`TerraformRuntime` calls.

    Two hooks:

    - :meth:`start` — emit a ``queued`` ledger row BEFORE the executor
      dispatches. The runtime stamps ``user_id`` / ``approver_user_id``
      / ``experiment_id`` / ``test_id`` here.
    - :meth:`finish` — emit the final result. ``status`` is one of
      ``succeeded`` / ``failed`` / ``halted`` / ``rejected``.

    Both methods MUST NOT raise — the audit boundary contract is that
    a misconfigured sink can never crash the runtime.
    """

    def start(self, *, run_id: str, spec: TerraformStackSpec, kind: TerraformRunKind, **ctx: Any) -> None: ...

    def finish(self, *, result: TerraformRunResult, **ctx: Any) -> None: ...

    def close(self) -> None: ...


class NullTerraformAuditSink:
    """No-op sink — used as a default so callers don't need to None-check."""

    def start(self, *, run_id: str, spec: TerraformStackSpec, kind: TerraformRunKind, **ctx: Any) -> None:
        logger.debug("NullTerraformAuditSink.start run_id=%s kind=%s", run_id, kind.value)

    def finish(self, *, result: TerraformRunResult, **ctx: Any) -> None:
        logger.debug("NullTerraformAuditSink.finish run_id=%s status=%s", result.run_id, result.status.value)

    def close(self) -> None:
        return


class HttpTerraformAuditSink:
    """Posts ``TerraformRun`` rows to the monolith via authenticated HTTP.

    The transport is synchronous httpx; the M2M token is minted via the
    same :class:`M2MTokenBroker` the workload sink uses (rule 27).
    Token acquisition is best-effort — if it fails, the row is still
    POSTed without an ``Authorization`` header and the monolith's
    `/_internal/audit/terraform-runs` route logs a warning + drops the
    row (the deployment is misconfigured but the runtime keeps running).
    """

    def __init__(
        self,
        *,
        url: str,
        broker: Any,
        audience: str,
        timeout_seconds: float = 5.0,
        scopes: tuple[str, ...] = (),
    ) -> None:
        self._url = url
        self._broker = broker
        self._audience = audience
        self._scopes = scopes
        self._timeout = timeout_seconds
        self._client = httpx.Client(timeout=timeout_seconds)
        self._lock = threading.Lock()

    def start(
        self,
        *,
        run_id: str,
        spec: TerraformStackSpec,
        kind: TerraformRunKind,
        **ctx: Any,
    ) -> None:
        body = {
            "phase": "start",
            "run_id": run_id,
            "run_kind": kind.value,
            "stack_name": spec.stack_name,
            "workspace_id": spec.workspace_id,
            "state_backend": spec.state_backend.value,
            "spec_hash": spec.compute_hash(),
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "user_id": ctx.get("user_id"),
            "approver_user_id": ctx.get("approver_user_id"),
            "experiment_id": ctx.get("experiment_id"),
            "test_id": ctx.get("test_id"),
            "request_id": ctx.get("request_id"),
            "org_id": ctx.get("org_id"),
        }
        self._post(body, phase="start")

    def finish(self, *, result: TerraformRunResult, **ctx: Any) -> None:
        body = {
            "phase": "finish",
            **result.model_dump(mode="json"),
            "request_id": ctx.get("request_id"),
            "org_id": ctx.get("org_id"),
        }
        self._post(body, phase="finish")

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass

    def _bearer(self) -> str | None:
        try:
            grant = _run_in_loop(
                self._broker.acquire(audience=self._audience, scopes=self._scopes)
            )
            return getattr(grant, "access_token", None)
        except Exception:  # noqa: BLE001
            logger.warning(
                "HttpTerraformAuditSink could not mint bearer for %s; row will be posted unauthenticated",
                self._audience,
                exc_info=True,
            )
            return None

    def _post(self, body: dict[str, Any], *, phase: str) -> None:
        bearer = self._bearer()
        headers = {"Content-Type": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            with self._lock:
                response = self._client.post(self._url, json=body, headers=headers)
            if response.status_code >= 400:
                logger.warning(
                    "HttpTerraformAuditSink POST %s phase=%s -> HTTP %s body=%s",
                    self._url,
                    phase,
                    response.status_code,
                    response.text[:512],
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "HttpTerraformAuditSink POST %s phase=%s failed: %s",
                self._url,
                phase,
                exc,
            )


def _run_in_loop(coro: Any) -> Any:
    """Run an async coroutine from a sync caller.

    Audit-sink calls are synchronous (the protocol does not return
    awaitables) but :class:`M2MTokenBroker.acquire` is async. Mirror
    the helper from :mod:`aqp_cp.services.http_audit_sink` so the
    two sinks behave identically on the threading axis.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=10.0)
    return asyncio.run(coro)


__all__ = [
    "HttpTerraformAuditSink",
    "NullTerraformAuditSink",
    "TerraformAuditSink",
]
